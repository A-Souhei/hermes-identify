from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from embedder import embed_texts, search_vectors
from models import Chunk, Entity, Image
from models import chunk_entities as ce_table


async def semantic_search(topic_id: str, query: str, limit: int, db: AsyncSession) -> dict:

    vectors = await embed_texts([query])
    if not vectors:
        return {"entities": [], "images": []}

    results = await search_vectors(vectors[0], topic_id, limit * 3)

    entity_scores: dict = {}
    image_scores: dict = {}

    for result in results:
        point_id = str(result.id)
        score = float(result.score)
        point_type = (result.payload or {}).get("type", "chunk")

        if point_type == "chunk":
            chunk = await db.get(Chunk, point_id)
            if not chunk:
                continue
            ent_res = await db.execute(
                select(Entity)
                .join(ce_table, Entity.id == ce_table.c.entity_id)
                .where(ce_table.c.chunk_id == point_id)
                .options(selectinload(Entity.images))
            )
            for ent in ent_res.scalars().all():
                if ent.id not in entity_scores or entity_scores[ent.id]["score"] < score:
                    entity_scores[ent.id] = {
                        "score": score,
                        "entity": ent,
                        "matched_excerpt": chunk.content[:300],
                    }

        elif point_type == "image":
            img = await db.get(Image, point_id)
            if img:
                if img.id not in image_scores or image_scores[img.id]["score"] < score:
                    image_scores[img.id] = {"score": score, "image": img}

    entity_hits = sorted(entity_scores.values(), key=lambda x: -x["score"])[:limit]
    image_hits = sorted(image_scores.values(), key=lambda x: -x["score"])[:limit]

    return {"entities": entity_hits, "images": image_hits}
