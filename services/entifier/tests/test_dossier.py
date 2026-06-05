"""Tests for dossier CRUD and block management."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import SubTopic


class TestDossierCRUD:
    async def test_create_dossier(self, client: AsyncClient):
        r = await client.post("/dossiers", json={"name": "My Dossier"})
        assert r.status_code == 201
        d = r.json()
        assert d["name"] == "My Dossier"
        assert "id" in d
        assert "created_at" in d
        assert "updated_at" in d

    async def test_list_dossiers(self, client: AsyncClient):
        await client.post("/dossiers", json={"name": "Alpha"})
        await client.post("/dossiers", json={"name": "Beta"})
        r = await client.get("/dossiers")
        assert r.status_code == 200
        names = [d["name"] for d in r.json()]
        assert "Alpha" in names
        assert "Beta" in names

    async def test_get_dossier_detail(self, client: AsyncClient):
        cr = await client.post("/dossiers", json={"name": "Detail Test"})
        did = cr.json()["id"]
        r = await client.get(f"/dossiers/{did}")
        assert r.status_code == 200
        assert r.json()["name"] == "Detail Test"
        assert r.json()["blocks"] == []

    async def test_get_dossier_not_found(self, client: AsyncClient):
        r = await client.get("/dossiers/nonexistent-id")
        assert r.status_code == 404

    async def test_rename_dossier(self, client: AsyncClient):
        cr = await client.post("/dossiers", json={"name": "Old Name"})
        did = cr.json()["id"]
        r = await client.patch(f"/dossiers/{did}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    async def test_delete_dossier(self, client: AsyncClient):
        cr = await client.post("/dossiers", json={"name": "To Delete"})
        did = cr.json()["id"]
        r = await client.delete(f"/dossiers/{did}")
        assert r.status_code == 204
        r2 = await client.get(f"/dossiers/{did}")
        assert r2.status_code == 404

    async def test_create_dossier_empty_name_rejected(self, client: AsyncClient):
        r = await client.post("/dossiers", json={"name": ""})
        assert r.status_code == 422

    async def test_create_dossier_name_too_long_rejected(self, client: AsyncClient):
        r = await client.post("/dossiers", json={"name": "x" * 201})
        assert r.status_code == 422


class TestDossierBlocks:
    async def _make_dossier(self, client: AsyncClient) -> str:
        r = await client.post("/dossiers", json={"name": "Test Dossier"})
        return r.json()["id"]

    async def _make_topic(self, client: AsyncClient) -> str:
        r = await client.post("/topics", json={"name": "Test Topic"})
        return r.json()["id"]

    async def _make_subtopic(self, topic_id: str, db_session: AsyncSession) -> str:
        """Insert a subtopic directly — no HTTP endpoint exists for subtopic creation."""
        st = SubTopic(topic_id=topic_id, name="Sub")
        db_session.add(st)
        await db_session.commit()
        await db_session.refresh(st)
        return st.id

    async def test_add_subtopic_block(self, client: AsyncClient, db_session: AsyncSession):
        did = await self._make_dossier(client)
        tid = await self._make_topic(client)
        sid = await self._make_subtopic(tid, db_session)
        r = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": sid, "order_index": 0},
        )
        assert r.status_code == 201
        b = r.json()
        assert b["block_type"] == "subtopic"
        assert b["label"] == "Sub"
        assert b["ref_id"] == sid

    async def test_topic_block_type_rejected(self, client: AsyncClient):
        did = await self._make_dossier(client)
        tid = await self._make_topic(client)
        r = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "topic", "ref_id": tid, "order_index": 0},
        )
        assert r.status_code == 422

    async def test_invalid_block_type_rejected(self, client: AsyncClient):
        did = await self._make_dossier(client)
        r = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "banana", "ref_id": "x", "order_index": 0},
        )
        assert r.status_code == 422

    async def test_duplicate_block_rejected(self, client: AsyncClient, db_session: AsyncSession):
        did = await self._make_dossier(client)
        tid = await self._make_topic(client)
        sid = await self._make_subtopic(tid, db_session)
        await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": sid, "order_index": 0},
        )
        r = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": sid, "order_index": 1},
        )
        assert r.status_code == 409

    async def test_nonexistent_ref_resolves_as_deleted(self, client: AsyncClient):
        did = await self._make_dossier(client)
        r = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": "ghost-id", "order_index": 0},
        )
        assert r.status_code == 201
        assert r.json()["label"] == "(deleted)"

    async def test_remove_block(self, client: AsyncClient, db_session: AsyncSession):
        did = await self._make_dossier(client)
        tid = await self._make_topic(client)
        sid = await self._make_subtopic(tid, db_session)
        br = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": sid, "order_index": 0},
        )
        block_id = br.json()["id"]
        r = await client.delete(f"/dossiers/{did}/blocks/{block_id}")
        assert r.status_code == 204
        detail = await client.get(f"/dossiers/{did}")
        assert detail.json()["blocks"] == []

    async def test_remove_block_idor_protection(self, client: AsyncClient, db_session: AsyncSession):
        did1 = await self._make_dossier(client)
        did2 = await self._make_dossier(client)
        tid = await self._make_topic(client)
        sid = await self._make_subtopic(tid, db_session)
        br = await client.post(
            f"/dossiers/{did1}/blocks",
            json={"block_type": "subtopic", "ref_id": sid, "order_index": 0},
        )
        block_id = br.json()["id"]
        # Try to delete block from did1 via did2's URL
        r = await client.delete(f"/dossiers/{did2}/blocks/{block_id}")
        assert r.status_code == 404

    async def test_reorder_block(self, client: AsyncClient, db_session: AsyncSession):
        did = await self._make_dossier(client)
        tid = await self._make_topic(client)
        sid = await self._make_subtopic(tid, db_session)
        br = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": sid, "order_index": 0},
        )
        block_id = br.json()["id"]
        r = await client.patch(
            f"/dossiers/{did}/blocks/{block_id}",
            json={"order_index": 5},
        )
        assert r.status_code == 200
        assert r.json()["order_index"] == 5

    async def test_negative_order_index_rejected(self, client: AsyncClient):
        did = await self._make_dossier(client)
        r = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": "x", "order_index": -1},
        )
        assert r.status_code == 422

    async def test_delete_dossier_cascades_blocks(self, client: AsyncClient, db_session: AsyncSession):
        did = await self._make_dossier(client)
        tid = await self._make_topic(client)
        sid = await self._make_subtopic(tid, db_session)
        br = await client.post(
            f"/dossiers/{did}/blocks",
            json={"block_type": "subtopic", "ref_id": sid, "order_index": 0},
        )
        block_id = br.json()["id"]
        await client.delete(f"/dossiers/{did}")
        # Block should not be reachable via a different dossier
        did2 = (await client.post("/dossiers", json={"name": "D2"})).json()["id"]
        r = await client.delete(f"/dossiers/{did2}/blocks/{block_id}")
        assert r.status_code == 404
