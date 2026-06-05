import io
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from pypdf import PdfWriter

DUMMY_VECTOR = [0.0] * 1536
DUMMY_EMBEDDINGS = [DUMMY_VECTOR]
DUMMY_DESCRIPTION = "A detailed image showing a chart with data."


def _make_blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture()
def mock_externals():
    with (
        patch("storage.upload_file", new_callable=AsyncMock, return_value="test/key"),
        patch("embedder.embed_texts", new_callable=AsyncMock, return_value=DUMMY_EMBEDDINGS),
        patch("embedder.upsert_to_qdrant", new_callable=AsyncMock),
        patch("embedder.describe_image", new_callable=AsyncMock, return_value=DUMMY_DESCRIPTION),
    ):
        yield


# ── Chunker unit tests (pure, no mocks) ─────────────────────────────────────

class TestChunkText:
    def test_empty_returns_empty(self):
        from ingestor import chunk_text
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        from ingestor import chunk_text
        result = chunk_text("Hello world")
        assert result == ["Hello world"]

    def test_long_text_produces_multiple_chunks(self):
        from ingestor import chunk_text
        text = "word " * 2000
        chunks = chunk_text(text)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        from ingestor import chunk_text
        text = "paragraph one. " * 400 + "paragraph two. " * 400
        chunks = chunk_text(text)
        assert len(chunks) >= 2
        # overlap means end of first chunk shares content with start of second
        assert chunks[0][-50:] in chunks[1] or chunks[1][:50] in chunks[0]

    def test_no_empty_chunks(self):
        from ingestor import chunk_text
        text = "\n\n".join(["word " * 300] * 5)
        assert all(c.strip() for c in chunk_text(text))


# ── Parser unit tests ────────────────────────────────────────────────────────

class TestParseMd:
    def test_utf8_decoded(self):
        from ingestor import parse_md
        result = parse_md(b"# Hello\nWorld")
        assert result == "# Hello\nWorld"

    def test_strips_whitespace(self):
        from ingestor import parse_md
        assert parse_md(b"  hello  ") == "hello"


class TestParsePdf:
    async def test_returns_text_and_page_count(self):
        from ingestor import parse_pdf
        pdf_bytes = _make_blank_pdf()
        text, pages = await parse_pdf(pdf_bytes)
        assert isinstance(text, str)
        assert pages == 1

    async def test_invalid_pdf_raises(self):
        from ingestor import parse_pdf
        with pytest.raises(Exception):
            await parse_pdf(b"not a pdf")


class TestParseCsv:
    def test_returns_decoded_text(self):
        from ingestor import parse_csv
        csv_bytes = b"name,age\nAlice,30\nBob,25"
        result = parse_csv(csv_bytes)
        assert "name,age" in result
        assert "Alice,30" in result

    def test_strips_whitespace(self):
        from ingestor import parse_csv
        assert parse_csv(b"  a,b  ") == "a,b"


class TestParseJson:
    def test_pretty_prints_valid_json(self):
        from ingestor import parse_json
        result = parse_json(b'{"key": "value", "num": 42}')
        assert '"key": "value"' in result
        assert '"num": 42' in result

    def test_invalid_json_falls_back_to_raw(self):
        from ingestor import parse_json
        raw = b"not valid json at all"
        assert parse_json(raw) == "not valid json at all"


class TestParseYaml:
    def test_returns_decoded_text(self):
        from ingestor import parse_yaml
        yaml_bytes = b"key: value\nlist:\n  - a\n  - b"
        result = parse_yaml(yaml_bytes)
        assert "key: value" in result
        assert "- a" in result

    def test_strips_whitespace(self):
        from ingestor import parse_yaml
        assert parse_yaml(b"  key: val  ") == "key: val"


# ── Ingest file endpoint ─────────────────────────────────────────────────────

class TestIngestFile:
    async def test_ingest_md_creates_document(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("doc.md", b"# Hello\nSome content here.", "text/markdown")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["topic_id"] == tid
        assert data["filename"] == "doc.md"
        assert data["source_type"] == "file"

    async def test_ingest_pdf_creates_document(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        pdf_bytes = _make_blank_pdf()
        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("report.pdf", pdf_bytes, "application/pdf")},
        )
        assert r.status_code == 201
        assert r.json()["filename"] == "report.pdf"

    async def test_ingest_csv_creates_document(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("data.csv", b"col1,col2\nval1,val2", "text/csv")},
        )
        assert r.status_code == 201
        assert r.json()["filename"] == "data.csv"

    async def test_ingest_json_creates_document(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("config.json", b'{"key": "value"}', "application/json")},
        )
        assert r.status_code == 201
        assert r.json()["filename"] == "config.json"

    async def test_ingest_yaml_creates_document(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("spec.yaml", b"key: value\n", "application/yaml")},
        )
        assert r.status_code == 201
        assert r.json()["filename"] == "spec.yaml"

    async def test_ingest_yml_creates_document(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("spec.yml", b"key: value\n", "application/yaml")},
        )
        assert r.status_code == 201
        assert r.json()["filename"] == "spec.yml"

    async def test_unsupported_format_returns_422(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("doc.docx", b"content", "application/octet-stream")},
        )
        assert r.status_code == 422

    async def test_ingest_file_topic_not_found(self, client: AsyncClient, mock_externals):
        r = await client.post(
            "/topics/nonexistent/ingest/file",
            files={"file": ("doc.md", b"content", "text/markdown")},
        )
        assert r.status_code == 404


# ── Ingest URL endpoint ──────────────────────────────────────────────────────

class TestIngestUrl:
    async def test_ingest_url_creates_document(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        with patch("ingestor.fetch_url", new_callable=AsyncMock, return_value="# Page content"):
            r = await client.post(
                f"/topics/{tid}/ingest/url",
                json={"url": "https://example.com/page"},
            )

        assert r.status_code == 201
        data = r.json()
        assert data["source_type"] == "url"
        assert data["source_ref"] == "https://example.com/page"

    async def test_ingest_url_topic_not_found(self, client: AsyncClient, mock_externals):
        with patch("ingestor.fetch_url", new_callable=AsyncMock, return_value="content"):
            r = await client.post(
                "/topics/nonexistent/ingest/url",
                json={"url": "https://example.com"},
            )
        assert r.status_code == 404


# ── Ingest image endpoint ────────────────────────────────────────────────────

class TestIngestImage:
    async def test_ingest_png_creates_image(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/image",
            files={"file": ("chart.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "image/png")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["filename"] == "chart.png"
        assert data["description"] == DUMMY_DESCRIPTION

    async def test_unsupported_image_format_returns_422(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]

        r = await client.post(
            f"/topics/{tid}/ingest/image",
            files={"file": ("file.bmp", b"content", "image/bmp")},
        )
        assert r.status_code == 422

    async def test_ingest_image_topic_not_found(self, client: AsyncClient, mock_externals):
        r = await client.post(
            "/topics/nonexistent/ingest/image",
            files={"file": ("img.png", b"content", "image/png")},
        )
        assert r.status_code == 404


# ── List endpoints ───────────────────────────────────────────────────────────

class TestListDocuments:
    async def test_empty_list(self, client: AsyncClient):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        r = await client.get(f"/topics/{tid}/documents")
        assert r.status_code == 200
        assert r.json() == []

    async def test_lists_after_ingest(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("a.md", b"content a", "text/markdown")},
        )
        await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("b.md", b"content b", "text/markdown")},
        )
        r = await client.get(f"/topics/{tid}/documents")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_topic_not_found_returns_404(self, client: AsyncClient):
        r = await client.get("/topics/nope/documents")
        assert r.status_code == 404


class TestListImages:
    async def test_empty_list(self, client: AsyncClient):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        r = await client.get(f"/topics/{tid}/images")
        assert r.status_code == 200
        assert r.json() == []

    async def test_lists_after_ingest(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        await client.post(
            f"/topics/{tid}/ingest/image",
            files={"file": ("img.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "image/png")},
        )
        r = await client.get(f"/topics/{tid}/images")
        assert r.status_code == 200
        assert len(r.json()) == 1

    async def test_topic_not_found_returns_404(self, client: AsyncClient):
        r = await client.get("/topics/nope/images")
        assert r.status_code == 404


# ── Get image content endpoint ────────────────────────────────────────────────

class TestGetImageContent:
    async def test_returns_image_bytes(self, client: AsyncClient, mock_externals):
        topic_r = await client.post("/topics", json={"name": "T"})
        tid = topic_r.json()["id"]
        img_r = await client.post(
            f"/topics/{tid}/ingest/image",
            files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "image/png")},
        )
        img_id = img_r.json()["id"]
        FAKE_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

        with patch("storage.download_file", new_callable=AsyncMock, return_value=FAKE_BYTES):
            r = await client.get(f"/images/{img_id}/content")

        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")
        assert r.content == FAKE_BYTES

    async def test_returns_404_for_unknown_image(self, client: AsyncClient):
        r = await client.get("/images/nonexistent/content")
        assert r.status_code == 404

    async def test_returns_404_when_no_minio_key(self, client: AsyncClient, db_session):
        from models import Image as ImageModel
        img = ImageModel(
            id="img-no-key", topic_id="t1",
            filename="photo.png", file_path="",
        )
        db_session.add(img)
        await db_session.commit()
        r = await client.get("/images/img-no-key/content")
        assert r.status_code == 404
