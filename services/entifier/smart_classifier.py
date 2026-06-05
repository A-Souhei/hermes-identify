import json
import logging
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


CLASSIFY_PROMPT = """\
You are classifying a document into a knowledge topic.

Existing topics:
{topics_list}

Document filename: {filename}
Document preview (first ~1500 chars):
{preview}

Return a JSON object in exactly this shape:
{{
  "action": "existing" | "new",
  "topic_id": "<id of existing topic, or null if action is new>",
  "topic_name": "<name for new topic, or null if action is existing>",
  "topic_description": "<one-sentence description for new topic, or null if action is existing>"
}}

Rules:
- If the document clearly fits one of the existing topics, set action="existing" and topic_id to that topic's id.
- If no existing topic fits well, set action="new" and provide a concise topic_name (3-6 words) and topic_description.
- topic_id must be null when action is "new".
- topic_name and topic_description must be null when action is "existing"."""


def _get_openai():
    cached = getattr(_get_openai, "_client", None)
    if cached is None:
        from openai import AsyncOpenAI
        cached = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-placeholder",
            base_url=settings.openai_base_url,
        )
        _get_openai._client = cached
    return cached


async def classify_topic(
    filename: str,
    preview: str,
    existing_topics: list[dict],
) -> dict:
    """Classify a document against existing topics or propose a new one.

    Returns a dict with keys: action, topic_id, topic_name, topic_description.
    """
    if existing_topics:
        topics_list = "\n".join(
            f"- id={t['id']} | name={t['name']} | description={t.get('description') or 'n/a'}"
            for t in existing_topics
        )
    else:
        topics_list = "(none — this will be the first topic)"

    prompt = CLASSIFY_PROMPT.format(
        topics_list=topics_list,
        filename=filename,
        preview=preview,
    )

    try:
        response = await _get_openai().chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=512,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as exc:
        logger.warning("classify_topic failed (%s: %s) — falling back to new topic", type(exc).__name__, exc)
        data = {}

    action = data.get("action", "new")
    # Validate: if action=existing but topic_id not in known ids, fall back to new
    known_ids = {t["id"] for t in existing_topics}
    if action == "existing" and data.get("topic_id") not in known_ids:
        action = "new"
        data["action"] = "new"
        data["topic_id"] = None

    if action not in ("existing", "new"):
        action = "new"

    return {
        "action": action,
        "topic_id": data.get("topic_id") if action == "existing" else None,
        "topic_name": data.get("topic_name") if action == "new" else None,
        "topic_description": data.get("topic_description") if action == "new" else None,
    }
