import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


class TestTopicLinks:
    async def test_list_empty(self, client: AsyncClient):
        r = await client.post("/topics", json={"name": "Link Empty"})
        tid = r.json()["id"]
        r2 = await client.get(f"/topics/{tid}/links")
        assert r2.status_code == 200
        assert r2.json() == []

    async def test_add_link_symmetric(self, client: AsyncClient):
        ta = (await client.post("/topics", json={"name": "LA"})).json()["id"]
        tb = (await client.post("/topics", json={"name": "LB"})).json()["id"]

        r = await client.post(f"/topics/{ta}/links", json={"linked_topic_id": tb})
        assert r.status_code == 201
        assert r.json()["id"] == tb

        assert any(t["id"] == tb for t in (await client.get(f"/topics/{ta}/links")).json())
        assert any(t["id"] == ta for t in (await client.get(f"/topics/{tb}/links")).json())

    async def test_duplicate_409(self, client: AsyncClient):
        ta = (await client.post("/topics", json={"name": "Dup A"})).json()["id"]
        tb = (await client.post("/topics", json={"name": "Dup B"})).json()["id"]
        await client.post(f"/topics/{ta}/links", json={"linked_topic_id": tb})
        r = await client.post(f"/topics/{ta}/links", json={"linked_topic_id": tb})
        assert r.status_code == 409

    async def test_reverse_duplicate_409(self, client: AsyncClient):
        ta = (await client.post("/topics", json={"name": "Rev A"})).json()["id"]
        tb = (await client.post("/topics", json={"name": "Rev B"})).json()["id"]
        await client.post(f"/topics/{ta}/links", json={"linked_topic_id": tb})
        r = await client.post(f"/topics/{tb}/links", json={"linked_topic_id": ta})
        assert r.status_code == 409

    async def test_self_link_422(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "Self"})).json()["id"]
        r = await client.post(f"/topics/{tid}/links", json={"linked_topic_id": tid})
        assert r.status_code == 422

    async def test_remove_link(self, client: AsyncClient):
        ta = (await client.post("/topics", json={"name": "Del A"})).json()["id"]
        tb = (await client.post("/topics", json={"name": "Del B"})).json()["id"]
        await client.post(f"/topics/{ta}/links", json={"linked_topic_id": tb})

        r = await client.delete(f"/topics/{ta}/links/{tb}")
        assert r.status_code == 204

        links = (await client.get(f"/topics/{ta}/links")).json()
        assert links == []

    async def test_remove_reverse_link(self, client: AsyncClient):
        ta = (await client.post("/topics", json={"name": "Rdel A"})).json()["id"]
        tb = (await client.post("/topics", json={"name": "Rdel B"})).json()["id"]
        await client.post(f"/topics/{ta}/links", json={"linked_topic_id": tb})

        r = await client.delete(f"/topics/{tb}/links/{ta}")
        assert r.status_code == 204
        assert (await client.get(f"/topics/{tb}/links")).json() == []

    async def test_remove_nonexistent_204(self, client: AsyncClient):
        ta = (await client.post("/topics", json={"name": "NoDel A"})).json()["id"]
        tb = (await client.post("/topics", json={"name": "NoDel B"})).json()["id"]
        r = await client.delete(f"/topics/{ta}/links/{tb}")
        assert r.status_code == 204

    async def test_link_unknown_topic_404(self, client: AsyncClient):
        ta = (await client.post("/topics", json={"name": "Known"})).json()["id"]
        r = await client.post(f"/topics/{ta}/links", json={"linked_topic_id": "no-such-id"})
        assert r.status_code == 404

    async def test_list_links_unknown_topic_404(self, client: AsyncClient):
        r = await client.get("/topics/no-such-id/links")
        assert r.status_code == 404


class TestIngestContext:
    @staticmethod
    def _file_mocks():
        return (
            patch("storage.upload_file", new_callable=AsyncMock),
            patch("ingestor.parse_md", return_value="doc content"),
            patch("ingestor.chunk_text", return_value=["doc content"]),
            patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]),
            patch("embedder.upsert_to_qdrant", new_callable=AsyncMock),
        )

    @staticmethod
    def _url_mocks():
        return (
            patch("storage.upload_file", new_callable=AsyncMock),
            patch("ingestor.fetch_url", new_callable=AsyncMock, return_value="fetched content"),
            patch("ingestor.chunk_text", return_value=["fetched content"]),
            patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]),
            patch("embedder.upsert_to_qdrant", new_callable=AsyncMock),
        )

    @staticmethod
    def _image_mocks(description="LLM description"):
        return (
            patch("storage.upload_file", new_callable=AsyncMock),
            patch("embedder.describe_image", new_callable=AsyncMock, return_value=description),
            patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]),
            patch("embedder.upsert_to_qdrant", new_callable=AsyncMock),
        )

    async def test_file_context_stored(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "FC"})).json()["id"]
        with patch("storage.upload_file", new_callable=AsyncMock), \
             patch("ingestor.parse_md", return_value="text"), \
             patch("ingestor.chunk_text", return_value=["text"]), \
             patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]), \
             patch("embedder.upsert_to_qdrant", new_callable=AsyncMock):
            r = await client.post(
                f"/topics/{tid}/ingest/file",
                files={"file": ("doc.md", b"# Doc", "text/markdown")},
                data={"context": "Research notes"},
            )
        assert r.status_code == 201
        assert r.json()["context"] == "Research notes"

    async def test_file_no_context_null(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "FNC"})).json()["id"]
        with patch("storage.upload_file", new_callable=AsyncMock), \
             patch("ingestor.parse_md", return_value="text"), \
             patch("ingestor.chunk_text", return_value=["text"]), \
             patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]), \
             patch("embedder.upsert_to_qdrant", new_callable=AsyncMock):
            r = await client.post(
                f"/topics/{tid}/ingest/file",
                files={"file": ("doc.md", b"# Doc", "text/markdown")},
            )
        assert r.status_code == 201
        assert r.json()["context"] is None

    async def test_file_context_too_long_422(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "FCL"})).json()["id"]
        r = await client.post(
            f"/topics/{tid}/ingest/file",
            files={"file": ("doc.md", b"# Doc", "text/markdown")},
            data={"context": "x" * 1001},
        )
        assert r.status_code == 422

    async def test_url_context_stored(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "UC"})).json()["id"]
        with patch("storage.upload_file", new_callable=AsyncMock), \
             patch("ingestor.fetch_url", new_callable=AsyncMock, return_value="page text"), \
             patch("ingestor.chunk_text", return_value=["page text"]), \
             patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]), \
             patch("embedder.upsert_to_qdrant", new_callable=AsyncMock):
            r = await client.post(
                f"/topics/{tid}/ingest/url",
                json={"url": "https://example.com", "context": "URL notes"},
            )
        assert r.status_code == 201
        assert r.json()["context"] == "URL notes"

    async def test_url_context_too_long_422(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "UCL"})).json()["id"]
        r = await client.post(
            f"/topics/{tid}/ingest/url",
            json={"url": "https://example.com", "context": "y" * 1001},
        )
        assert r.status_code == 422

    async def test_image_preserves_llm_description(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "IC"})).json()["id"]
        with patch("storage.upload_file", new_callable=AsyncMock), \
             patch("embedder.describe_image", new_callable=AsyncMock, return_value="AI desc"), \
             patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]), \
             patch("embedder.upsert_to_qdrant", new_callable=AsyncMock):
            r = await client.post(
                f"/topics/{tid}/ingest/image",
                files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
                data={"context": "image notes"},
            )
        assert r.status_code == 201
        assert r.json()["description"] == "AI desc"

    async def test_image_no_context(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "INC"})).json()["id"]
        with patch("storage.upload_file", new_callable=AsyncMock), \
             patch("embedder.describe_image", new_callable=AsyncMock, return_value="Only AI"), \
             patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 10]), \
             patch("embedder.upsert_to_qdrant", new_callable=AsyncMock):
            r = await client.post(
                f"/topics/{tid}/ingest/image",
                files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
            )
        assert r.status_code == 201
        assert r.json()["description"] == "Only AI"

    async def test_image_context_too_long_422(self, client: AsyncClient):
        tid = (await client.post("/topics", json={"name": "ICL"})).json()["id"]
        r = await client.post(
            f"/topics/{tid}/ingest/image",
            files={"file": ("photo.png", b"\x89PNG\r\n", "image/png")},
            data={"context": "z" * 1001},
        )
        assert r.status_code == 422
