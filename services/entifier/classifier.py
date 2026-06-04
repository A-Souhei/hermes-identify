import json
import random

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

DISCOVERY_PROMPT = """\
You are analyzing text excerpts from a document corpus. Identify the distinct sub-topics.

Return a JSON object in exactly this shape:
{{
  "subtopics": [
    {{"name": "Short name (2-5 words)", "description": "One sentence.", "keywords": ["kw1", "kw2"]}}
  ]
}}

Rules:
- Between 3 and 12 sub-topics.
- Each sub-topic must be meaningfully distinct.
- No duplicate names.

Text excerpts:
{excerpts}"""

ASSIGNMENT_PROMPT = """\
Classify each numbered excerpt into 1 or 2 of the sub-topics listed below.

Sub-topics:
{subtopics}

Return a JSON object in exactly this shape:
{{
  "assignments": [
    {{"subtopic_names": ["Sub-topic name"]}},
    ...
  ]
}}

One entry per excerpt, in the same order. Use exact sub-topic names from the list above.

Excerpts:
{excerpts}"""


def _get_openai():
    _cache = getattr(_get_openai, "_client", None)
    if _cache is None:
        from openai import AsyncOpenAI
        _cache = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-placeholder",
            base_url=settings.openai_base_url,
        )
        _get_openai._client = _cache
    return _cache


async def discover_subtopics(chunks: list, topic_id: str, db: AsyncSession) -> list:
    from models import SubTopic

    sample = random.sample(chunks, min(30, len(chunks)))
    excerpts = "\n\n---\n\n".join(c.content[:500] for c in sample)

    response = await _get_openai().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{"role": "user", "content": DISCOVERY_PROMPT.format(excerpts=excerpts)}],
        response_format={"type": "json_object"},
        max_tokens=2000,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    items = data.get("subtopics", [])

    subtopics = []
    for item in items:
        st = SubTopic(
            topic_id=topic_id,
            name=item["name"],
            description=item.get("description"),
            keywords=json.dumps(item.get("keywords", [])),
        )
        db.add(st)
        subtopics.append(st)

    await db.flush()
    return subtopics


async def assign_chunks_to_subtopics(chunks: list, subtopics: list, db: AsyncSession) -> None:
    from models import chunk_subtopics as cs_table

    if not subtopics:
        return

    subtopic_map = {st.name: st for st in subtopics}
    subtopic_list = "\n".join(f"- {st.name}: {st.description or ''}" for st in subtopics)

    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        excerpts = "\n\n".join(f"[{j + 1}] {c.content[:400]}" for j, c in enumerate(batch))

        response = await _get_openai().chat.completions.create(
            model=settings.openai_chat_model,
            messages=[{
                "role": "user",
                "content": ASSIGNMENT_PROMPT.format(subtopics=subtopic_list, excerpts=excerpts),
            }],
            response_format={"type": "json_object"},
            max_tokens=2000,
        )

        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        assignments = data.get("assignments", [])

        for chunk, assignment in zip(batch, assignments):
            for name in assignment.get("subtopic_names", []):
                st = subtopic_map.get(name)
                if st:
                    existing = await db.execute(
                        cs_table.select().where(
                            cs_table.c.chunk_id == chunk.id,
                            cs_table.c.subtopic_id == st.id,
                        )
                    )
                    if not existing.first():
                        await db.execute(
                            cs_table.insert().values(chunk_id=chunk.id, subtopic_id=st.id)
                        )

    await db.flush()
