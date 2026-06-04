import json

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings


def _get_openai():
    from openai import AsyncOpenAI
    cached = getattr(_get_openai, "_client", None)
    if cached is None:
        cached = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-placeholder",
            base_url=settings.openai_base_url,
        )
        _get_openai._client = cached
    return cached


INDEX_PROMPT = """\
You are organizing knowledge entities into document sections for the sub-topic: "{subtopic_name}".

Group the entities below into 2 to 5 coherent sections that would form logical chapters or sections
in a document about this sub-topic. Each section should cluster related entities together.

Entities:
{entity_list}

Return a JSON object in exactly this shape:
{{
  "sections": [
    {{
      "name": "Section name (3-7 words)",
      "description": "One sentence describing what this section covers.",
      "order_index": 0,
      "entity_names": ["Exact Entity Name 1", "Exact Entity Name 2"]
    }}
  ]
}}

Rules:
- 2 to 5 sections total.
- order_index starts at 0 and increments by 1.
- entity_names must match the entity names exactly as given above.
- Every entity should appear in at least one section.
"""


async def index_subtopic(subtopic, entities: list, db: AsyncSession) -> list:
    """Group entities into sections for one sub-topic."""
    from models import Section

    if not entities:
        return []

    entity_list = "\n".join(f"- {e.name}: {e.description or ''}" for e in entities)

    response = await _get_openai().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{
            "role": "user",
            "content": INDEX_PROMPT.format(
                subtopic_name=subtopic.name,
                entity_list=entity_list,
            ),
        }],
        response_format={"type": "json_object"},
        max_tokens=2000,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    sections_data = data.get("sections", [])

    entity_map = {e.name: e for e in entities}

    sections = []
    for i, sec_data in enumerate(sections_data):
        section = Section(
            topic_id=subtopic.topic_id,
            subtopic_id=subtopic.id,
            name=sec_data["name"],
            description=sec_data.get("description"),
            order_index=sec_data.get("order_index", i),
        )
        db.add(section)
        await db.flush()

        for ent_name in sec_data.get("entity_names", []):
            entity = entity_map.get(ent_name)
            if entity:
                entity.section_id = section.id

        sections.append(section)

    await db.flush()
    return sections


async def index_all_subtopics(subtopics: list, topic_id: str, db: AsyncSession) -> None:
    """Run index_subtopic for every sub-topic."""
    from models import Entity
    from sqlalchemy import select

    for subtopic in subtopics:
        result = await db.execute(
            select(Entity).where(Entity.subtopic_id == subtopic.id)
        )
        entities = result.scalars().all()
        await index_subtopic(subtopic, entities, db)
