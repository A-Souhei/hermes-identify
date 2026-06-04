from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import insert

from models import Chunk, Document, Entity, Image, SourceType, Topic, chunk_entities


DUMMY_VECTOR = [0.0] * 1536


def _qdrant_hit(point_id: str, score: float, point_type: str, topic_id: str):
    hit = MagicMock()
    hit.id = point_id
    hit.score = score
    hit.payload = {"type": point_type, "topic_id": topic_id}
    return hit


@pytest.fixture()
async def seeded_search(db_session):
    """Topic with one chunk→entity link and one image."""
    topic = Topic(id="topic-s", name="Search Test")
    db_session.add(topic)
    doc = Document(
        id="doc-s", topic_id="topic-s",
        source_type=SourceType.FILE, source_ref="f.md", filename="f.md",
    )
    db_session.add(doc)
    chunk = Chunk(
        id="chunk-s", document_id="doc-s", topic_id="topic-s",
        content="Carbon emissions are rising rapidly.", chunk_index=0,
    )
    db_session.add(chunk)
    entity = Entity(
        id="ent-s", topic_id="topic-s",
        name="Carbon Emissions", ref_id="ENT-000001",
    )
    db_session.add(entity)
    image = Image(
        id="img-s", topic_id="topic-s",
        filename="chart.png", file_path="topic-s/images/img-s/chart.png",
        description="A bar chart showing rising CO2 levels.",
    )
    db_session.add(image)
    await db_session.flush()
    await db_session.execute(
        insert(chunk_entities).values(chunk_id="chunk-s", entity_id="ent-s")
    )
    await db_session.commit()
    return {"topic_id": "topic-s", "chunk_id": "chunk-s", "entity_id": "ent-s", "image_id": "img-s"}


class TestSearch:
    async def test_topic_not_found(self, client: AsyncClient):
        r = await client.post("/topics/nope/search", json={"query": "climate", "limit": 5})
        assert r.status_code == 404

    async def test_empty_when_no_qdrant_results(self, client: AsyncClient, seeded_search):
        with (
            patch("search.embed_texts", new_callable=AsyncMock, return_value=[DUMMY_VECTOR]),
            patch("search.search_vectors", new_callable=AsyncMock, return_value=[]),
        ):
            r = await client.post("/topics/topic-s/search", json={"query": "nothing", "limit": 5})
        assert r.status_code == 200
        assert r.json() == {"entities": [], "images": []}

    async def test_entity_hit_from_chunk(self, client: AsyncClient, seeded_search):
        hit = _qdrant_hit("chunk-s", 0.95, "chunk", "topic-s")
        with (
            patch("search.embed_texts", new_callable=AsyncMock, return_value=[DUMMY_VECTOR]),
            patch("search.search_vectors", new_callable=AsyncMock, return_value=[hit]),
        ):
            r = await client.post("/topics/topic-s/search", json={"query": "carbon", "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert len(data["entities"]) == 1
        assert data["entities"][0]["entity"]["id"] == "ent-s"
        assert data["entities"][0]["score"] == pytest.approx(0.95)
        assert "Carbon emissions" in data["entities"][0]["matched_excerpt"]
        assert data["images"] == []

    async def test_image_hit(self, client: AsyncClient, seeded_search):
        hit = _qdrant_hit("img-s", 0.88, "image", "topic-s")
        with (
            patch("search.embed_texts", new_callable=AsyncMock, return_value=[DUMMY_VECTOR]),
            patch("search.search_vectors", new_callable=AsyncMock, return_value=[hit]),
        ):
            r = await client.post("/topics/topic-s/search", json={"query": "chart", "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert len(data["images"]) == 1
        assert data["images"][0]["image"]["id"] == "img-s"
        assert data["images"][0]["score"] == pytest.approx(0.88)
        assert data["entities"] == []

    async def test_deduplicates_entity_keeps_max_score(self, client: AsyncClient, seeded_search, db_session):
        chunk2 = Chunk(
            id="chunk-s2", document_id="doc-s", topic_id="topic-s",
            content="CO2 budget is shrinking.", chunk_index=1,
        )
        db_session.add(chunk2)
        await db_session.flush()
        await db_session.execute(
            insert(chunk_entities).values(chunk_id="chunk-s2", entity_id="ent-s")
        )
        await db_session.commit()

        hits = [
            _qdrant_hit("chunk-s", 0.70, "chunk", "topic-s"),
            _qdrant_hit("chunk-s2", 0.92, "chunk", "topic-s"),
        ]
        with (
            patch("search.embed_texts", new_callable=AsyncMock, return_value=[DUMMY_VECTOR]),
            patch("search.search_vectors", new_callable=AsyncMock, return_value=hits),
        ):
            r = await client.post("/topics/topic-s/search", json={"query": "carbon", "limit": 5})
        assert r.status_code == 200
        data = r.json()
        assert len(data["entities"]) == 1
        assert data["entities"][0]["score"] == pytest.approx(0.92)

    async def test_unknown_chunk_id_skipped(self, client: AsyncClient, seeded_search):
        hit = _qdrant_hit("nonexistent-chunk", 0.99, "chunk", "topic-s")
        with (
            patch("search.embed_texts", new_callable=AsyncMock, return_value=[DUMMY_VECTOR]),
            patch("search.search_vectors", new_callable=AsyncMock, return_value=[hit]),
        ):
            r = await client.post("/topics/topic-s/search", json={"query": "test", "limit": 5})
        assert r.status_code == 200
        assert r.json()["entities"] == []

    async def test_limit_respected(self, client: AsyncClient, seeded_search, db_session):
        for i in range(5):
            c = Chunk(id=f"chunk-lim-{i}", document_id="doc-s", topic_id="topic-s",
                      content=f"content {i}", chunk_index=i + 10)
            e = Entity(id=f"ent-lim-{i}", topic_id="topic-s",
                       name=f"Entity {i}", ref_id=f"ENT-LIM{i:03d}")
            db_session.add(c)
            db_session.add(e)
        await db_session.flush()
        for i in range(5):
            await db_session.execute(
                insert(chunk_entities).values(chunk_id=f"chunk-lim-{i}", entity_id=f"ent-lim-{i}")
            )
        await db_session.commit()

        hits = [_qdrant_hit(f"chunk-lim-{i}", 0.9 - i * 0.1, "chunk", "topic-s") for i in range(5)]
        with (
            patch("search.embed_texts", new_callable=AsyncMock, return_value=[DUMMY_VECTOR]),
            patch("search.search_vectors", new_callable=AsyncMock, return_value=hits),
        ):
            r = await client.post("/topics/topic-s/search", json={"query": "test", "limit": 3})
        assert r.status_code == 200
        assert len(r.json()["entities"]) <= 3
