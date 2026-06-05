"""Tests verifying context is required for image ingest."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

DUMMY_VECTOR = [0.0] * 1536
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20


@pytest.fixture()
def mock_image_externals():
    with (
        patch("storage.upload_file", new_callable=AsyncMock, return_value="test/key"),
        patch("embedder.embed_texts", new_callable=AsyncMock, return_value=[DUMMY_VECTOR]),
        patch("embedder.upsert_to_qdrant", new_callable=AsyncMock),
        patch("embedder.describe_image", new_callable=AsyncMock, return_value="AI description"),
    ):
        yield


class TestImageIngestContext:
    async def test_context_required(self, client: AsyncClient):
        """Image upload without context returns 422."""
        tr = await client.post("/topics", json={"name": "T"})
        tid = tr.json()["id"]
        r = await client.post(
            f"/topics/{tid}/ingest/image",
            files={"file": ("chart.png", PNG_BYTES, "image/png")},
        )
        assert r.status_code == 422

    async def test_empty_context_rejected(self, client: AsyncClient, mock_image_externals):
        """Image upload with blank context returns 422."""
        tr = await client.post("/topics", json={"name": "T"})
        tid = tr.json()["id"]
        r = await client.post(
            f"/topics/{tid}/ingest/image",
            data={"context": "   "},
            files={"file": ("chart.png", PNG_BYTES, "image/png")},
        )
        assert r.status_code == 422

    async def test_context_too_long_rejected(self, client: AsyncClient):
        """Context exceeding 5000 chars returns 422."""
        tr = await client.post("/topics", json={"name": "T"})
        tid = tr.json()["id"]
        r = await client.post(
            f"/topics/{tid}/ingest/image",
            data={"context": "x" * 5001},
            files={"file": ("chart.png", PNG_BYTES, "image/png")},
        )
        assert r.status_code == 422

    async def test_valid_context_stores_description(self, client: AsyncClient, mock_image_externals):
        """Context is stored as image description."""
        tr = await client.post("/topics", json={"name": "T"})
        tid = tr.json()["id"]
        r = await client.post(
            f"/topics/{tid}/ingest/image",
            data={"context": "A bar chart showing CO2 levels from 2000 to 2024."},
            files={"file": ("chart.png", PNG_BYTES, "image/png")},
        )
        assert r.status_code == 201
        assert r.json()["description"] == "A bar chart showing CO2 levels from 2000 to 2024."
