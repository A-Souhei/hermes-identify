import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from models import (
    Chunk, Document, Entity, EntityType, Job, JobStatus,
    Section, SourceType, SubTopic, Topic,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_llm_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


INDEX_JSON = json.dumps({
    "sections": [
        {
            "name": "Foundations of Climate Science",
            "description": "Core scientific concepts.",
            "order_index": 0,
            "entity_names": ["Carbon Budget"],
        },
        {
            "name": "Emission Trajectories",
            "description": "Projected pathways.",
            "order_index": 1,
            "entity_names": ["Emission Pathway"],
        },
    ]
})


@pytest.fixture()
def mock_indexer_llm():
    mock_create = AsyncMock(return_value=_make_llm_response(INDEX_JSON))
    with patch("indexer._get_openai") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        mock_get.return_value = mock_client
        yield mock_create


@pytest.fixture()
async def seeded_with_entities(db_session):
    """Seed a topic with a subtopic and two entities (no sections yet)."""
    topic = Topic(id="topic-e", name="Climate")
    db_session.add(topic)
    doc = Document(
        id="doc-e", topic_id="topic-e",
        source_type=SourceType.FILE, source_ref="f.md", filename="f.md",
    )
    db_session.add(doc)
    st = SubTopic(id="st-e", topic_id="topic-e", name="Climate Science", description="Science")
    db_session.add(st)
    chunk = Chunk(id="ch-e-0", document_id="doc-e", topic_id="topic-e",
                  content="text", chunk_index=0)
    db_session.add(chunk)
    ent1 = Entity(id="ent-e-1", topic_id="topic-e", subtopic_id="st-e",
                  name="Carbon Budget", ref_id="ENT-000001")
    ent2 = Entity(id="ent-e-2", topic_id="topic-e", subtopic_id="st-e",
                  name="Emission Pathway", ref_id="ENT-000002")
    db_session.add(ent1)
    db_session.add(ent2)
    await db_session.commit()
    return {"topic": topic, "subtopic": st, "entities": [ent1, ent2]}


# ── index_subtopic unit tests ─────────────────────────────────────────────────

class TestIndexSubtopic:
    async def test_creates_sections(self, db_session, seeded_with_entities, mock_indexer_llm):
        from indexer import index_subtopic
        st = seeded_with_entities["subtopic"]
        entities = seeded_with_entities["entities"]

        sections = await index_subtopic(st, entities, db_session)
        await db_session.commit()

        assert len(sections) == 2
        assert sections[0].name == "Foundations of Climate Science"
        assert sections[0].order_index == 0
        assert sections[1].name == "Emission Trajectories"
        assert sections[1].order_index == 1

    async def test_assigns_entities_to_sections(self, db_session, seeded_with_entities, mock_indexer_llm):
        from indexer import index_subtopic
        from sqlalchemy import select

        entities = seeded_with_entities["entities"]
        await index_subtopic(seeded_with_entities["subtopic"], entities, db_session)
        await db_session.commit()

        for ent in entities:
            await db_session.refresh(ent)
        assert entities[0].section_id is not None
        assert entities[1].section_id is not None
        assert entities[0].section_id != entities[1].section_id

    async def test_empty_entities_returns_empty(self, db_session, seeded_with_entities, mock_indexer_llm):
        from indexer import index_subtopic
        result = await index_subtopic(seeded_with_entities["subtopic"], [], db_session)
        assert result == []
        mock_indexer_llm.assert_not_called()


# ── Section list endpoint ─────────────────────────────────────────────────────

class TestListSections:
    async def test_empty_before_index(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-ls", name="T")
        db_session.add(topic)
        st = SubTopic(id="st-ls", topic_id="topic-ls", name="S", description="d")
        db_session.add(st)
        await db_session.commit()

        r = await client.get("/subtopics/st-ls/sections")
        assert r.status_code == 200
        assert r.json() == []

    async def test_subtopic_not_found(self, client: AsyncClient):
        assert (await client.get("/subtopics/nope/sections")).status_code == 404

    async def test_lists_sections_ordered(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-lo", name="T")
        db_session.add(topic)
        st = SubTopic(id="st-lo", topic_id="topic-lo", name="S", description="d")
        db_session.add(st)
        s1 = Section(id="s-lo-1", topic_id="topic-lo", subtopic_id="st-lo",
                     name="B Section", order_index=1)
        s2 = Section(id="s-lo-2", topic_id="topic-lo", subtopic_id="st-lo",
                     name="A Section", order_index=0)
        db_session.add(s1)
        db_session.add(s2)
        await db_session.commit()

        r = await client.get("/subtopics/st-lo/sections")
        assert r.status_code == 200
        names = [s["name"] for s in r.json()]
        assert names == ["A Section", "B Section"]


# ── Section patch endpoint ────────────────────────────────────────────────────

class TestPatchSection:
    async def test_rename_section(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-ps", name="T")
        db_session.add(topic)
        st = SubTopic(id="st-ps", topic_id="topic-ps", name="S", description="d")
        db_session.add(st)
        s = Section(id="s-ps", topic_id="topic-ps", subtopic_id="st-ps",
                    name="Old", order_index=0)
        db_session.add(s)
        await db_session.commit()

        r = await client.patch("/sections/s-ps", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    async def test_update_order(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-uo", name="T")
        db_session.add(topic)
        st = SubTopic(id="st-uo", topic_id="topic-uo", name="S", description="d")
        db_session.add(st)
        s = Section(id="s-uo", topic_id="topic-uo", subtopic_id="st-uo",
                    name="S", order_index=0)
        db_session.add(s)
        await db_session.commit()

        r = await client.patch("/sections/s-uo", json={"order_index": 3})
        assert r.status_code == 200
        assert r.json()["order_index"] == 3

    async def test_section_not_found(self, client: AsyncClient):
        assert (await client.patch("/sections/nope", json={"name": "X"})).status_code == 404


# ── Index endpoint ────────────────────────────────────────────────────────────

class TestTopicIndex:
    async def test_empty_index(self, client: AsyncClient):
        r = await client.post("/topics", json={"name": "T"})
        tid = r.json()["id"]
        resp = await client.get(f"/topics/{tid}/index")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic_id"] == tid
        assert data["subtopics"] == []

    async def test_topic_not_found(self, client: AsyncClient):
        assert (await client.get("/topics/nope/index")).status_code == 404

    async def test_full_index_structure(self, client: AsyncClient, db_session):
        topic = Topic(id="topic-idx", name="Climate Report")
        db_session.add(topic)
        st = SubTopic(id="st-idx", topic_id="topic-idx", name="Science", description="d")
        db_session.add(st)
        sec = Section(id="sec-idx", topic_id="topic-idx", subtopic_id="st-idx",
                      name="Foundations", order_index=0)
        db_session.add(sec)
        ent = Entity(id="ent-idx", topic_id="topic-idx", subtopic_id="st-idx",
                     section_id="sec-idx", name="Carbon Budget", ref_id="ENT-ABCDEF")
        db_session.add(ent)
        await db_session.commit()

        resp = await client.get("/topics/topic-idx/index")
        assert resp.status_code == 200
        data = resp.json()
        assert data["topic_name"] == "Climate Report"
        assert len(data["subtopics"]) == 1
        assert data["subtopics"][0]["name"] == "Science"
        assert len(data["subtopics"][0]["sections"]) == 1
        assert data["subtopics"][0]["sections"][0]["name"] == "Foundations"
        assert len(data["subtopics"][0]["sections"][0]["entities"]) == 1
        assert data["subtopics"][0]["sections"][0]["entities"][0]["ref_id"] == "ENT-ABCDEF"


# ── Full pipeline integration ─────────────────────────────────────────────────

class TestFullPipelineWithIndex:
    async def test_process_creates_sections(self, test_engine, db_session, mock_indexer_llm):
        from main import _run_process_job
        from models import chunk_subtopics
        from sqlalchemy import insert, select
        from unittest.mock import AsyncMock, patch

        topic = Topic(id="topic-pi", name="T")
        db_session.add(topic)
        doc = Document(id="doc-pi", topic_id="topic-pi",
                       source_type=SourceType.FILE, source_ref="f.md", filename="f.md")
        db_session.add(doc)
        job = Job(id="job-pi", topic_id="topic-pi", type="process", status=JobStatus.PENDING)
        db_session.add(job)
        chunk = Chunk(id="ch-pi", document_id="doc-pi", topic_id="topic-pi",
                      content="text", chunk_index=0)
        db_session.add(chunk)
        await db_session.commit()

        # discover/entify run inside the job (after the re-process cleanup), so they
        # create the subtopic and entities rather than rely on pre-seeded rows.
        async def fake_discover(chunks_arg, topic_id, db):
            st = SubTopic(id="st-pi", topic_id=topic_id, name="Climate Science", description="Sci")
            db.add(st)
            await db.flush()
            await db.execute(insert(chunk_subtopics).values(chunk_id="ch-pi", subtopic_id="st-pi"))
            return [st]

        async def fake_entify(subtopics, topic_id, db):
            db.add(Entity(id="ent-pi-1", topic_id=topic_id, subtopic_id="st-pi",
                          name="Carbon Budget", ref_id="ENT-000001"))
            db.add(Entity(id="ent-pi-2", topic_id=topic_id, subtopic_id="st-pi",
                          name="Emission Pathway", ref_id="ENT-000002"))
            await db.flush()

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        with (
            patch("classifier.discover_subtopics", side_effect=fake_discover),
            patch("classifier.assign_chunks_to_subtopics", AsyncMock()),
            patch("entifier.entify_all_subtopics", side_effect=fake_entify),
        ):
            await _run_process_job("job-pi", session_factory=session_factory)

        await db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED

        sections = (await db_session.execute(
            select(Section).where(Section.topic_id == "topic-pi")
        )).scalars().all()
        assert len(sections) == 2

        entities = (await db_session.execute(
            select(Entity).where(Entity.topic_id == "topic-pi")
        )).scalars().all()
        assert len(entities) == 2
        assert all(e.section_id is not None for e in entities)
