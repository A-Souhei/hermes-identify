import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from models import Chunk, Document, Entity, EntityType, Job, JobStatus, SourceType, SubTopic, Topic


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_llm_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


ENTITIES_JSON = json.dumps({
    "entities": [
        {
            "name": "Carbon Budget",
            "description": "The total CO2 that can be emitted.",
            "type": "concept",
            "supporting_chunk_indices": [0],
        },
        {
            "name": "Emission Pathway",
            "description": "A projected trajectory of emissions.",
            "type": "finding",
            "supporting_chunk_indices": [1],
        },
    ]
})


@pytest.fixture()
def mock_entify_llm():
    mock_create = AsyncMock(return_value=_make_llm_response(ENTITIES_JSON))
    with patch("entifier._get_openai") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        mock_get.return_value = mock_client
        yield mock_create


@pytest.fixture()
async def seeded(db_session):
    """Seed a topic with a subtopic and two chunks already assigned to it."""
    topic = Topic(id="topic-d", name="Climate")
    db_session.add(topic)
    doc = Document(
        id="doc-d", topic_id="topic-d",
        source_type=SourceType.FILE, source_ref="f.md", filename="f.md",
    )
    db_session.add(doc)
    st = SubTopic(id="st-d", topic_id="topic-d", name="Climate Science", description="Science")
    db_session.add(st)

    chunks = [
        Chunk(id=f"chunk-d-{i}", document_id="doc-d", topic_id="topic-d",
              content=f"excerpt {i}", chunk_index=i)
        for i in range(2)
    ]
    for c in chunks:
        db_session.add(c)

    await db_session.flush()

    from models import chunk_subtopics
    from sqlalchemy import insert
    for c in chunks:
        await db_session.execute(
            insert(chunk_subtopics).values(chunk_id=c.id, subtopic_id=st.id)
        )

    await db_session.commit()
    return {"topic": topic, "subtopic": st, "chunks": chunks}


# ── entify_subtopic unit test ─────────────────────────────────────────────────

class TestEntifySubtopic:
    async def test_creates_entities_with_ref_id(self, db_session, seeded, mock_entify_llm):
        from entifier import entify_subtopic
        from sqlalchemy import select

        st = seeded["subtopic"]
        chunks = seeded["chunks"]

        entities = await entify_subtopic(st, chunks, db_session)
        await db_session.commit()

        assert len(entities) == 2
        assert all(e.ref_id.startswith("ENT-") for e in entities)
        assert entities[0].name == "Carbon Budget"
        assert entities[0].entity_type == EntityType.CONCEPT
        assert entities[1].entity_type == EntityType.FINDING

    async def test_links_chunks_to_entities(self, db_session, seeded, mock_entify_llm):
        from entifier import entify_subtopic
        from models import chunk_entities
        from sqlalchemy import select

        entities = await entify_subtopic(seeded["subtopic"], seeded["chunks"], db_session)
        await db_session.commit()

        rows = (await db_session.execute(select(chunk_entities))).fetchall()
        assert len(rows) == 2  # each entity linked to one chunk

    async def test_empty_chunks_returns_empty(self, db_session, seeded, mock_entify_llm):
        from entifier import entify_subtopic
        result = await entify_subtopic(seeded["subtopic"], [], db_session)
        assert result == []
        mock_entify_llm.assert_not_called()


# ── List entities endpoint ─────────────────────────────────────────────────────

class TestListEntities:
    async def test_empty_before_process(self, client: AsyncClient):
        r = await client.post("/topics", json={"name": "T"})
        tid = r.json()["id"]
        resp = await client.get(f"/topics/{tid}/entities")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_topic_not_found(self, client: AsyncClient):
        assert (await client.get("/topics/nope/entities")).status_code == 404

    async def test_lists_entities(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-le", name="T")
        db_session.add(topic)
        st = SubTopic(id="st-le", topic_id="topic-le", name="S", description="d")
        db_session.add(st)
        ent = Entity(topic_id="topic-le", subtopic_id="st-le",
                     name="MyEntity", ref_id="ENT-ABC123")
        db_session.add(ent)
        await db_session.commit()

        resp = await client.get("/topics/topic-le/entities")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "MyEntity"
        assert resp.json()[0]["ref_id"] == "ENT-ABC123"

    async def test_filter_by_subtopic(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-fs", name="T")
        db_session.add(topic)
        st1 = SubTopic(id="st-fs-1", topic_id="topic-fs", name="S1", description="d")
        st2 = SubTopic(id="st-fs-2", topic_id="topic-fs", name="S2", description="d")
        db_session.add(st1)
        db_session.add(st2)
        ent1 = Entity(topic_id="topic-fs", subtopic_id="st-fs-1", name="E1", ref_id="ENT-000001")
        ent2 = Entity(topic_id="topic-fs", subtopic_id="st-fs-2", name="E2", ref_id="ENT-000002")
        db_session.add(ent1)
        db_session.add(ent2)
        await db_session.commit()

        resp = await client.get(f"/topics/topic-fs/entities?subtopic_id=st-fs-1")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "E1"


# ── Get entity detail endpoint ────────────────────────────────────────────────

class TestGetEntity:
    async def test_get_entity_detail(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-ge", name="T")
        db_session.add(topic)
        st = SubTopic(id="st-ge", topic_id="topic-ge", name="S", description="d")
        db_session.add(st)
        ent = Entity(id="ent-ge", topic_id="topic-ge", subtopic_id="st-ge",
                     name="MyEntity", ref_id="ENT-ABCDEF")
        db_session.add(ent)
        await db_session.commit()

        resp = await client.get("/entities/ent-ge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "ent-ge"
        assert data["ref_id"] == "ENT-ABCDEF"
        assert "chunks" in data
        assert "images" in data

    async def test_entity_not_found(self, client: AsyncClient):
        assert (await client.get("/entities/nope")).status_code == 404


# ── Patch entity endpoint ─────────────────────────────────────────────────────

class TestPatchEntity:
    async def test_rename(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-pe", name="T")
        db_session.add(topic)
        ent = Entity(id="ent-pe", topic_id="topic-pe", name="Old", ref_id="ENT-000000")
        db_session.add(ent)
        await db_session.commit()

        resp = await client.patch("/entities/ent-pe", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_change_type(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-ct", name="T")
        db_session.add(topic)
        ent = Entity(id="ent-ct", topic_id="topic-ct", name="E", ref_id="ENT-000001")
        db_session.add(ent)
        await db_session.commit()

        resp = await client.patch("/entities/ent-ct", json={"entity_type": "methodology"})
        assert resp.status_code == 200
        assert resp.json()["entity_type"] == "methodology"

    async def test_reassign_subtopic(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-rs", name="T")
        db_session.add(topic)
        st1 = SubTopic(id="st-rs-1", topic_id="topic-rs", name="S1", description="d")
        st2 = SubTopic(id="st-rs-2", topic_id="topic-rs", name="S2", description="d")
        db_session.add(st1)
        db_session.add(st2)
        ent = Entity(id="ent-rs", topic_id="topic-rs", subtopic_id="st-rs-1",
                     name="E", ref_id="ENT-000002")
        db_session.add(ent)
        await db_session.commit()

        resp = await client.patch("/entities/ent-rs", json={"subtopic_id": "st-rs-2"})
        assert resp.status_code == 200
        assert resp.json()["subtopic_id"] == "st-rs-2"

    async def test_entity_not_found(self, client: AsyncClient):
        assert (await client.patch("/entities/nope", json={"name": "X"})).status_code == 404


# ── Full pipeline integration test ────────────────────────────────────────────

class TestFullPipelineWithEntities:
    async def test_process_creates_entities(self, test_engine, db_session, mock_entify_llm):
        from main import _run_process_job
        from sqlalchemy import select

        # Mock classifier functions so only entify runs with the real code
        discover_mock = AsyncMock(return_value=[
            SubTopic(id="st-int", topic_id="topic-int", name="Climate Science", description="Sci")
        ])
        assign_mock = AsyncMock()

        topic = Topic(id="topic-int", name="T")
        db_session.add(topic)
        doc = Document(id="doc-int", topic_id="topic-int",
                       source_type=SourceType.FILE, source_ref="f.md", filename="f.md")
        db_session.add(doc)
        st = SubTopic(id="st-int", topic_id="topic-int", name="Climate Science", description="Sci")
        db_session.add(st)
        job = Job(id="job-int", topic_id="topic-int", type="process", status=JobStatus.PENDING)
        db_session.add(job)

        chunks = [
            Chunk(id=f"ch-int-{i}", document_id="doc-int", topic_id="topic-int",
                  content=f"text {i}", chunk_index=i)
            for i in range(2)
        ]
        for c in chunks:
            db_session.add(c)

        from models import chunk_subtopics
        from sqlalchemy import insert
        await db_session.flush()
        for c in chunks:
            await db_session.execute(
                insert(chunk_subtopics).values(chunk_id=c.id, subtopic_id="st-int")
            )
        await db_session.commit()

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        with (
            patch("classifier.discover_subtopics", discover_mock),
            patch("classifier.assign_chunks_to_subtopics", assign_mock),
        ):
            await _run_process_job("job-int", session_factory=session_factory)

        await db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED

        entities = (await db_session.execute(
            select(Entity).where(Entity.topic_id == "topic-int")
        )).scalars().all()
        assert len(entities) == 2
        assert all(e.ref_id.startswith("ENT-") for e in entities)
