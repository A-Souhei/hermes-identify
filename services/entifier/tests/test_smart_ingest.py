import io
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from pypdf import PdfWriter


def _make_blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


DUMMY_VECTOR = [0.0] * 1536
DUMMY_EMBEDDINGS = [DUMMY_VECTOR]

# A classify_topic response that matches an existing topic
_EXISTING_CLASSIFICATION = {
    "action": "existing",
    "topic_id": None,  # filled in dynamically per-test
    "topic_name": None,
    "topic_description": None,
}

# A classify_topic response that creates a new topic
_NEW_CLASSIFICATION = {
    "action": "new",
    "topic_id": None,
    "topic_name": "Climate Science",
    "topic_description": "Research on climate change and global warming.",
}

_BAD_JSON_CLASSIFICATION = {
    "action": "new",
    "topic_id": None,
    "topic_name": "sample_doc",
    "topic_description": None,
}


@pytest.fixture()
def mock_externals():
    with (
        patch("storage.upload_file", new_callable=AsyncMock, return_value="test/key"),
        patch("embedder.embed_texts", new_callable=AsyncMock, return_value=DUMMY_EMBEDDINGS),
        patch("embedder.upsert_to_qdrant", new_callable=AsyncMock),
    ):
        yield


class TestSmartIngestFile:
    async def test_md_matches_existing_topic(self, client: AsyncClient, mock_externals):
        """MD file classified into an existing topic returns was_created=False."""
        topic_r = await client.post("/topics", json={"name": "Climate Science"})
        tid = topic_r.json()["id"]

        classification = {**_EXISTING_CLASSIFICATION, "topic_id": tid}
        with patch("smart_classifier.classify_topic", new_callable=AsyncMock, return_value=classification):
            r = await client.post(
                "/smart-ingest/file",
                files={"file": ("report.md", b"# Climate\n\nGlobal temperatures are rising.", "text/markdown")},
            )

        assert r.status_code == 201
        data = r.json()
        assert data["topic_id"] == tid
        assert data["topic_name"] == "Climate Science"
        assert data["was_created"] is False
        assert data["filename"] == "report.md"
        assert "document_id" in data

    async def test_md_no_match_creates_new_topic(self, client: AsyncClient, mock_externals):
        """MD file with no matching topic creates a new topic and returns was_created=True."""
        with patch("smart_classifier.classify_topic", new_callable=AsyncMock, return_value=_NEW_CLASSIFICATION):
            r = await client.post(
                "/smart-ingest/file",
                files={"file": ("climate_report.md", b"# Climate\n\nRising temperatures worldwide.", "text/markdown")},
            )

        assert r.status_code == 201
        data = r.json()
        assert data["was_created"] is True
        assert data["topic_name"] == "Climate Science"
        assert data["filename"] == "climate_report.md"
        assert data["topic_id"] is not None
        assert data["document_id"] is not None

    async def test_invalid_extension_returns_422(self, client: AsyncClient):
        """Uploading a .docx file returns 422."""
        r = await client.post(
            "/smart-ingest/file",
            files={"file": ("doc.docx", b"content", "application/octet-stream")},
        )
        assert r.status_code == 422

    async def test_context_too_long_returns_422(self, client: AsyncClient):
        """Context exceeding 1000 chars returns 422."""
        r = await client.post(
            "/smart-ingest/file",
            data={"context": "x" * 1001},
            files={"file": ("doc.md", b"# Hello", "text/markdown")},
        )
        assert r.status_code == 422

    async def test_llm_bad_json_falls_back_to_new_topic(self, client: AsyncClient, mock_externals):
        """When classify_topic returns a fallback (bad JSON scenario), a new topic is created."""
        # Simulate the classifier returning the safe fallback dict
        fallback = {
            "action": "new",
            "topic_id": None,
            "topic_name": "sample_doc",
            "topic_description": None,
        }
        with patch("smart_classifier.classify_topic", new_callable=AsyncMock, return_value=fallback):
            r = await client.post(
                "/smart-ingest/file",
                files={"file": ("sample_doc.md", b"# Test\n\nSome content.", "text/markdown")},
            )

        assert r.status_code == 201
        data = r.json()
        assert data["was_created"] is True
        assert data["topic_name"] == "sample_doc"

    async def test_pdf_file_classified_and_ingested(self, client: AsyncClient, mock_externals):
        """PDF file is correctly parsed and classified."""
        pdf_bytes = _make_blank_pdf()
        with patch("smart_classifier.classify_topic", new_callable=AsyncMock, return_value=_NEW_CLASSIFICATION):
            r = await client.post(
                "/smart-ingest/file",
                files={"file": ("research.pdf", pdf_bytes, "application/pdf")},
            )

        assert r.status_code == 201
        data = r.json()
        assert data["filename"] == "research.pdf"
        assert data["was_created"] is True

    async def test_existing_topic_id_hallucinated_falls_back_to_new(self, client: AsyncClient, mock_externals):
        """When LLM returns a non-existent topic_id, we fall back to creating a new topic."""
        classification = {
            "action": "existing",
            "topic_id": "nonexistent-uuid-12345",
            "topic_name": None,
            "topic_description": None,
        }
        with patch("smart_classifier.classify_topic", new_callable=AsyncMock, return_value=classification):
            r = await client.post(
                "/smart-ingest/file",
                files={"file": ("doc.md", b"# Hello\n\nContent here.", "text/markdown")},
            )

        assert r.status_code == 201
        data = r.json()
        assert data["was_created"] is True

    async def test_csv_extension_returns_422(self, client: AsyncClient):
        """CSV files are not accepted by smart-ingest (only pdf/md)."""
        r = await client.post(
            "/smart-ingest/file",
            files={"file": ("data.csv", b"a,b,c", "text/csv")},
        )
        assert r.status_code == 422
