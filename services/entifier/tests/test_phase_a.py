import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine


class TestHealth:
    async def test_returns_ok(self, client: AsyncClient):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert r.json()["version"] == "0.1.0"


class TestTopicCreate:
    async def test_creates_topic(self, client: AsyncClient):
        r = await client.post("/topics", json={"name": "Climate Change", "description": "Research on climate"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Climate Change"
        assert data["description"] == "Research on climate"
        assert "id" in data
        assert "created_at" in data

    async def test_creates_topic_without_description(self, client: AsyncClient):
        r = await client.post("/topics", json={"name": "Minimal Topic"})
        assert r.status_code == 201
        assert r.json()["description"] is None

    async def test_name_required(self, client: AsyncClient):
        r = await client.post("/topics", json={"description": "no name"})
        assert r.status_code == 422


class TestTopicList:
    async def test_empty_list(self, client: AsyncClient):
        r = await client.get("/topics")
        assert r.status_code == 200
        assert r.json() == []

    async def test_returns_all_topics(self, client: AsyncClient):
        await client.post("/topics", json={"name": "Topic A"})
        await client.post("/topics", json={"name": "Topic B"})
        r = await client.get("/topics")
        assert r.status_code == 200
        names = [t["name"] for t in r.json()]
        assert "Topic A" in names
        assert "Topic B" in names


class TestTopicGet:
    async def test_get_existing(self, client: AsyncClient):
        create_r = await client.post("/topics", json={"name": "My Topic"})
        topic_id = create_r.json()["id"]
        r = await client.get(f"/topics/{topic_id}")
        assert r.status_code == 200
        assert r.json()["id"] == topic_id
        assert r.json()["name"] == "My Topic"

    async def test_get_nonexistent_returns_404(self, client: AsyncClient):
        r = await client.get("/topics/does-not-exist")
        assert r.status_code == 404


class TestSchemas:
    def test_topic_create_requires_name(self):
        from models import TopicCreate
        with pytest.raises(ValidationError):
            TopicCreate()

    def test_entity_patch_all_optional(self):
        from models import EntityPatch
        patch = EntityPatch()
        assert patch.name is None
        assert patch.description is None
        assert patch.entity_type is None
        assert patch.subtopic_id is None

    def test_subtopic_patch_all_optional(self):
        from models import SubTopicPatch
        patch = SubTopicPatch()
        assert patch.name is None
        assert patch.description is None


class TestDatabaseTables:
    async def test_all_tables_created(self, test_engine: AsyncEngine):
        from sqlalchemy import inspect

        async with test_engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )

        expected = {
            "topics", "documents", "chunks", "images",
            "subtopics", "sections", "entities", "jobs",
            "chunk_entities", "image_entities", "chunk_subtopics",
        }
        assert expected.issubset(set(table_names))
