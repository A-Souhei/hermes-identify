"""Tests for bundle ingest (ZIP with markdown + images) and document asset content."""
import io
import zipfile
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from models import DocumentAsset

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
MD_CONTENT = b"# Hello\n\n![Photo](images/a.png)\n"


def _make_zip(entries: dict[str, bytes]) -> bytes:
    """Build an in-memory ZIP from a {name: content} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture()
def mock_bundle_externals():
    with (
        patch("storage.upload_file", new_callable=AsyncMock, return_value="test/key"),
        patch("storage.download_file", new_callable=AsyncMock, return_value=PNG_BYTES),
        patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.0] * 1536]),
        patch("embedder.upsert_to_qdrant", new_callable=AsyncMock),
    ):
        yield


class TestBundleIngest:
    async def test_ingest_creates_document_and_asset(
        self, client: AsyncClient, mock_bundle_externals
    ):
        topic_r = await client.post("/topics", json={"name": "Bundle Topic"})
        tid = topic_r.json()["id"]

        zip_bytes = _make_zip({
            "doc.md": MD_CONTENT,
            "images/a.png": PNG_BYTES,
        })

        r = await client.post(
            f"/topics/{tid}/ingest/bundle",
            files={"file": ("bundle.zip", zip_bytes, "application/zip")},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["asset_count"] == 1
        assert data["document"]["filename"] == "doc.md"

    async def test_asset_rel_path_is_correct(
        self, client: AsyncClient, db_session, mock_bundle_externals
    ):
        topic_r = await client.post("/topics", json={"name": "Bundle Path"})
        tid = topic_r.json()["id"]

        zip_bytes = _make_zip({
            "doc.md": MD_CONTENT,
            "images/a.png": PNG_BYTES,
        })
        r = await client.post(
            f"/topics/{tid}/ingest/bundle",
            files={"file": ("bundle.zip", zip_bytes, "application/zip")},
        )
        assert r.status_code == 201
        doc_id = r.json()["document"]["id"]

        from sqlalchemy import select
        result = await db_session.execute(
            select(DocumentAsset).where(DocumentAsset.document_id == doc_id)
        )
        asset = result.scalar_one_or_none()
        assert asset is not None
        assert asset.rel_path == "images/a.png"
        assert asset.content_type == "image/png"

    async def test_asset_content_endpoint_returns_bytes(
        self, client: AsyncClient, mock_bundle_externals
    ):
        topic_r = await client.post("/topics", json={"name": "Bundle Content"})
        tid = topic_r.json()["id"]

        zip_bytes = _make_zip({
            "doc.md": MD_CONTENT,
            "images/a.png": PNG_BYTES,
        })
        bundle_r = await client.post(
            f"/topics/{tid}/ingest/bundle",
            files={"file": ("bundle.zip", zip_bytes, "application/zip")},
        )
        assert bundle_r.status_code == 201
        doc_id = bundle_r.json()["document"]["id"]

        # fetch asset id from DB
        from sqlalchemy import select
        # We need the db_session — use a separate fixture approach via the client
        # Instead, list assets by hitting the content endpoint discovered from DB.
        # We need the asset id; retrieve it via a direct DB query in the test engine.
        # Use the client's app dependency-overridden session.
        from main import app
        from db import get_session
        session_gen = app.dependency_overrides[get_session]()
        db = await session_gen.__anext__()
        result = await db.execute(
            select(DocumentAsset).where(DocumentAsset.document_id == doc_id)
        )
        asset = result.scalar_one()
        asset_id = asset.id

        r = await client.get(f"/documents/{doc_id}/assets/{asset_id}/content")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/png")
        assert r.content == PNG_BYTES

    async def test_asset_content_404_for_unknown(
        self, client: AsyncClient, mock_bundle_externals
    ):
        r = await client.get("/documents/no-doc/assets/no-asset/content")
        assert r.status_code == 404

    async def test_zip_slip_entry_is_skipped(
        self, client: AsyncClient, mock_bundle_externals
    ):
        topic_r = await client.post("/topics", json={"name": "Zip Slip"})
        tid = topic_r.json()["id"]

        zip_bytes = _make_zip({
            "doc.md": b"# Safe\n",
            "../evil.png": PNG_BYTES,
        })
        r = await client.post(
            f"/topics/{tid}/ingest/bundle",
            files={"file": ("bundle.zip", zip_bytes, "application/zip")},
        )
        # Request succeeds — the evil entry is silently skipped
        assert r.status_code == 201
        assert r.json()["asset_count"] == 0

    async def test_no_markdown_returns_422(
        self, client: AsyncClient, mock_bundle_externals
    ):
        topic_r = await client.post("/topics", json={"name": "No MD"})
        tid = topic_r.json()["id"]

        zip_bytes = _make_zip({"images/a.png": PNG_BYTES})
        r = await client.post(
            f"/topics/{tid}/ingest/bundle",
            files={"file": ("bundle.zip", zip_bytes, "application/zip")},
        )
        assert r.status_code == 422
        assert "no markdown" in r.json()["detail"]

    async def test_topic_not_found_returns_404(
        self, client: AsyncClient, mock_bundle_externals
    ):
        zip_bytes = _make_zip({"doc.md": b"# Hi\n"})
        r = await client.post(
            "/topics/nonexistent/ingest/bundle",
            files={"file": ("bundle.zip", zip_bytes, "application/zip")},
        )
        assert r.status_code == 404


class TestRewriteAssetLinks:
    def test_mapped_image_is_rewritten(self):
        from main import _rewrite_asset_links

        class _FakeAsset:
            id = "asset-1"

        assets_by_doc = {
            "doc-1": {
                "images/a.png": _FakeAsset(),
                "a.png": _FakeAsset(),
            }
        }
        result = _rewrite_asset_links("![x](images/a.png)", "doc-1", assets_by_doc)
        assert result == "![x](/documents/doc-1/assets/asset-1/content)"

    def test_unmapped_image_becomes_italic_caption(self):
        from main import _rewrite_asset_links

        result = _rewrite_asset_links("![y](images/missing.png)", "doc-1", {})
        assert result == "*y*"

    def test_external_url_left_untouched(self):
        from main import _rewrite_asset_links

        src = "![z](https://example.com/x.png)"
        result = _rewrite_asset_links(src, "doc-1", {})
        assert result == src

    def test_url_decoded_path_matches(self):
        from main import _rewrite_asset_links

        class _FakeAsset:
            id = "asset-2"

        assets_by_doc = {
            "doc-2": {
                "images/my image.png": _FakeAsset(),
                "my image.png": _FakeAsset(),
            }
        }
        result = _rewrite_asset_links("![a](images/my%20image.png)", "doc-2", assets_by_doc)
        assert result == "![a](/documents/doc-2/assets/asset-2/content)"

    def test_dotslash_prefix_stripped(self):
        from main import _rewrite_asset_links

        class _FakeAsset:
            id = "asset-3"

        assets_by_doc = {
            "doc-3": {
                "images/b.png": _FakeAsset(),
                "b.png": _FakeAsset(),
            }
        }
        result = _rewrite_asset_links("![b](./images/b.png)", "doc-3", assets_by_doc)
        assert result == "![b](/documents/doc-3/assets/asset-3/content)"
