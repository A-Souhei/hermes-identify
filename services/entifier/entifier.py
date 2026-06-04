import json

from sqlalchemy import select
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


ENTIFY_PROMPT = """\
You are extracting named knowledge entities from text excerpts about the sub-topic: "{subtopic_name}".

An entity is a distinct, nameable concept, finding, methodology, data source, case study, or framework.

Return a JSON object in exactly this shape:
{{
  "entities": [
    {{
      "name": "Entity name (2-6 words)",
      "description": "One or two sentences.",
      "type": "concept|methodology|data_source|case_study|finding|framework",
      "supporting_chunk_indices": [0, 2]
    }}
  ]
}}

Rules:
- 1 to 10 entities.
- Each entity must be meaningfully distinct.
- supporting_chunk_indices: 0-based indices into the excerpts below that support this entity.
- type must be exactly one of: concept, methodology, data_source, case_study, finding, framework.

Sub-topic: {subtopic_name}
Description: {subtopic_description}

Excerpts:
{excerpts}"""


async def entify_subtopic(subtopic, chunks: list, db: AsyncSession) -> list:
    """Extract entities for a single sub-topic from its assigned chunks."""
    from models import Entity, EntityType, chunk_entities as ce_table

    if not chunks:
        return []

    excerpts = "\n\n".join(f"[{i}] {c.content[:600]}" for i, c in enumerate(chunks))

    response = await _get_openai().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[{
            "role": "user",
            "content": ENTIFY_PROMPT.format(
                subtopic_name=subtopic.name,
                subtopic_description=subtopic.description or "",
                excerpts=excerpts,
            ),
        }],
        response_format={"type": "json_object"},
        max_tokens=2000,
    )

    raw = response.choices[0].message.content or "{}"
    data = json.loads(raw)
    items = data.get("entities", [])

    entities = []
    for item in items:
        entity_type = None
        try:
            entity_type = EntityType(item.get("type", ""))
        except ValueError:
            pass

        ent = Entity(
            topic_id=subtopic.topic_id,
            subtopic_id=subtopic.id,
            name=item["name"],
            description=item.get("description"),
            entity_type=entity_type,
            ref_id="placeholder",
        )
        db.add(ent)
        await db.flush()
        ent.ref_id = f"ENT-{ent.id[:6].upper()}"

        for idx in item.get("supporting_chunk_indices", []):
            if 0 <= idx < len(chunks):
                chunk = chunks[idx]
                existing = await db.execute(
                    ce_table.select().where(
                        ce_table.c.chunk_id == chunk.id,
                        ce_table.c.entity_id == ent.id,
                    )
                )
                if not existing.first():
                    await db.execute(
                        ce_table.insert().values(chunk_id=chunk.id, entity_id=ent.id)
                    )

        entities.append(ent)

    await db.flush()
    return entities


async def entify_all_subtopics(subtopics: list, topic_id: str, db: AsyncSession) -> None:
    """Run entity extraction for every sub-topic."""
    from models import Chunk, chunk_subtopics

    for subtopic in subtopics:
        result = await db.execute(
            select(Chunk)
            .join(chunk_subtopics, Chunk.id == chunk_subtopics.c.chunk_id)
            .where(chunk_subtopics.c.subtopic_id == subtopic.id)
        )
        chunks = result.scalars().all()
        await entify_subtopic(subtopic, chunks, db)
