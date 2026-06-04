import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from models import Chunk, Job, JobStatus, SubTopic


# ── LLM response helpers ──────────────────────────────────────────────────────

def _make_openai_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


SUBTOPICS_JSON = json.dumps({
    "subtopics": [
        {"name": "Climate Science", "description": "Scientific basis of climate.", "keywords": ["temperature", "CO2"]},
        {"name": "Policy Responses", "description": "Government and regulatory actions.", "keywords": ["policy", "law"]},
        {"name": "Economic Impact", "description": "Economic effects of climate change.", "keywords": ["cost", "GDP"]},
    ]
})

ASSIGNMENTS_JSON = json.dumps({
    "assignments": [
        {"subtopic_names": ["Climate Science"]},
        {"subtopic_names": ["Policy Responses"]},
    ]
})


@pytest.fixture()
def mock_llm():
    """Provides discovery response first, then assignment response.
    Used for full-pipeline tests (discover + assign) and discover-only tests."""
    responses = [
        _make_openai_response(SUBTOPICS_JSON),
        _make_openai_response(ASSIGNMENTS_JSON),
    ]
    mock_create = AsyncMock(side_effect=responses)
    with patch("classifier._get_openai") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        mock_get.return_value = mock_client
        yield mock_create


@pytest.fixture()
def mock_llm_assign_only():
    """Provides assignment response only — for tests that call assign_chunks_to_subtopics directly."""
    mock_create = AsyncMock(return_value=_make_openai_response(ASSIGNMENTS_JSON))
    with patch("classifier._get_openai") as mock_get:
        mock_client = MagicMock()
        mock_client.chat.completions.create = mock_create
        mock_get.return_value = mock_client
        yield mock_create


# ── Endpoint tests ────────────────────────────────────────────────────────────

class TestProcessEndpoint:
    async def test_creates_job(self, client: AsyncClient):
        topic_r = await client.post("/topics", json={"name": "Climate"})
        tid = topic_r.json()["id"]
        with patch("main._run_process_job", new_callable=AsyncMock):
            r = await client.post(f"/topics/{tid}/process")
        assert r.status_code == 202
        data = r.json()
        assert data["topic_id"] == tid
        assert data["status"] == "pending"
        assert "id" in data

    async def test_topic_not_found(self, client: AsyncClient):
        r = await client.post("/topics/nope/process")
        assert r.status_code == 404


class TestGetJob:
    async def test_get_existing_job(self, client: AsyncClient):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        with patch("main._run_process_job", new_callable=AsyncMock):
            job_r = await client.post(f"/topics/{tid}/process")
        job_id = job_r.json()["id"]
        r = await client.get(f"/jobs/{job_id}")
        assert r.status_code == 200
        assert r.json()["id"] == job_id

    async def test_job_not_found(self, client: AsyncClient):
        r = await client.get("/jobs/nonexistent")
        assert r.status_code == 404


class TestListSubtopics:
    async def test_empty_before_process(self, client: AsyncClient):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        r = await client.get(f"/topics/{tid}/subtopics")
        assert r.status_code == 200
        assert r.json() == []

    async def test_topic_not_found(self, client: AsyncClient):
        r = await client.get("/topics/nope/subtopics")
        assert r.status_code == 404


class TestPatchSubtopic:
    async def test_rename_subtopic(self, client: AsyncClient, db_session):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        st = SubTopic(topic_id=tid, name="Old Name", description="Old desc")
        db_session.add(st)
        await db_session.commit()
        await db_session.refresh(st)

        r = await client.patch(f"/subtopics/{st.id}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"
        assert r.json()["description"] == "Old desc"

    async def test_subtopic_not_found(self, client: AsyncClient):
        r = await client.patch("/subtopics/nope", json={"name": "X"})
        assert r.status_code == 404


# ── classifier unit tests ─────────────────────────────────────────────────────

class TestDiscoverSubtopics:
    async def test_creates_subtopics_in_db(self, db_session, mock_llm):
        from models import Document, SourceType, Topic

        topic = Topic(id="topic-1", name="Climate")
        db_session.add(topic)

        doc = Document(
            id="doc-1", topic_id="topic-1",
            source_type=SourceType.FILE,
            source_ref="test.md", filename="test.md",
        )
        db_session.add(doc)
        await db_session.flush()

        chunks = [
            Chunk(document_id="doc-1", topic_id="topic-1", content=f"Content {i}", chunk_index=i)
            for i in range(3)
        ]
        for c in chunks:
            db_session.add(c)
        await db_session.flush()

        from classifier import discover_subtopics
        subtopics = await discover_subtopics(chunks, "topic-1", db_session)

        assert len(subtopics) == 3
        assert subtopics[0].name == "Climate Science"
        assert subtopics[1].name == "Policy Responses"


class TestAssignChunks:
    async def test_assigns_chunks_to_subtopics(self, db_session, mock_llm_assign_only):
        from models import Document, SourceType, Topic, chunk_subtopics
        from sqlalchemy import select

        topic = Topic(id="topic-2", name="T")
        db_session.add(topic)
        doc = Document(
            id="doc-2", topic_id="topic-2",
            source_type=SourceType.FILE, source_ref="f.md", filename="f.md",
        )
        db_session.add(doc)
        await db_session.flush()

        chunks = [
            Chunk(document_id="doc-2", topic_id="topic-2", content=f"text {i}", chunk_index=i)
            for i in range(2)
        ]
        for c in chunks:
            db_session.add(c)

        st1 = SubTopic(topic_id="topic-2", name="Climate Science", description="Sci")
        st2 = SubTopic(topic_id="topic-2", name="Policy Responses", description="Policy")
        db_session.add(st1)
        db_session.add(st2)
        await db_session.flush()

        from classifier import assign_chunks_to_subtopics
        await assign_chunks_to_subtopics(chunks, [st1, st2], db_session)
        await db_session.flush()

        result = await db_session.execute(select(chunk_subtopics))
        rows = result.fetchall()
        assert len(rows) == 2


# ── Background job tests ──────────────────────────────────────────────────────

class TestRunProcessJob:
    async def test_completes_with_no_chunks(self, test_engine, db_session):
        from models import Topic
        from main import _run_process_job

        topic = Topic(id="topic-nc", name="T")
        db_session.add(topic)
        job = Job(id="job-nc", topic_id="topic-nc", type="process", status=JobStatus.PENDING)
        db_session.add(job)
        await db_session.commit()

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        await _run_process_job("job-nc", session_factory=session_factory)

        await db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED

    async def test_full_pipeline_with_mocked_llm(self, test_engine, db_session, mock_llm):
        from models import Document, SourceType, SubTopic, Topic, chunk_subtopics
        from main import _run_process_job
        from sqlalchemy import select

        topic = Topic(id="topic-fp", name="T")
        db_session.add(topic)
        doc = Document(
            id="doc-fp", topic_id="topic-fp",
            source_type=SourceType.FILE, source_ref="f.md", filename="f.md",
        )
        db_session.add(doc)
        job = Job(id="job-fp", topic_id="topic-fp", type="process", status=JobStatus.PENDING)
        db_session.add(job)

        chunks = [
            Chunk(document_id="doc-fp", topic_id="topic-fp", content=f"text {i}", chunk_index=i)
            for i in range(2)
        ]
        for c in chunks:
            db_session.add(c)
        await db_session.commit()

        session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        await _run_process_job("job-fp", session_factory=session_factory)

        await db_session.refresh(job)
        assert job.status == JobStatus.COMPLETED

        sts = (await db_session.execute(
            select(SubTopic).where(SubTopic.topic_id == "topic-fp")
        )).scalars().all()
        assert len(sts) == 3

        assignments = (await db_session.execute(select(chunk_subtopics))).fetchall()
        assert len(assignments) == 2
