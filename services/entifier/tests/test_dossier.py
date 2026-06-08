"""Tests for dossier CRUD and block management."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import Chunk, Document, Dossier, DossierBlock, Entity, SourceType, SubTopic, Topic, chunk_entities


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


# ── Pure helper unit tests ────────────────────────────────────────────────────

class TestCleanMarkdown:
    def test_strips_inline_footnote_refs(self):
        from main import _clean_markdown
        assert "[^1]" not in _clean_markdown("Hello[^1] world[^abc].")

    def test_drops_footnote_definition_lines(self):
        from main import _clean_markdown
        text = "Paragraph.\n\n[^1]: This is a footnote.\n\nMore text."
        result = _clean_markdown(text)
        assert "[^1]:" not in result
        assert "More text." in result

    def test_strips_html_tags_keeps_inner_text(self):
        from main import _clean_markdown
        assert _clean_markdown("<span class=\"mark\">™</span>") == "™"
        assert _clean_markdown("<u>8.2.1</u>") == "8.2.1"

    def test_html_table_tags_removed_leaving_cell_text(self):
        from main import _clean_markdown
        result = _clean_markdown("<td>data</td>")
        assert "data" in result
        assert "<td>" not in result

    def test_collapses_excess_newlines(self):
        from main import _clean_markdown
        result = _clean_markdown("a\n\n\n\n\nb")
        assert "\n\n\n" not in result
        assert "a" in result and "b" in result

    def test_preserves_markdown_syntax(self):
        from main import _clean_markdown
        text = "# Heading\n\n**bold** and *em*\n\n- item"
        result = _clean_markdown(text)
        assert "# Heading" in result
        assert "**bold**" in result
        assert "- item" in result

    def test_drops_trailing_dangling_heading(self):
        from main import _clean_markdown
        result = _clean_markdown("Body paragraph.\n\n***8.3.2 Dispositif de suivi***")
        assert "Dispositif" not in result
        assert result.rstrip().endswith("Body paragraph.")

    def test_keeps_heading_with_body_after(self):
        from main import _clean_markdown
        result = _clean_markdown("### **8.2 Title**\n\nReal body text.")
        assert "8.2 Title" in result
        assert "Real body text." in result

    def test_merges_bold_split_by_removed_tag(self):
        from main import _clean_markdown
        # "**Sah-AnAI**<span>™</span>**.**" -> after tag strip -> "**Sah-AnAI**™**.**"
        result = _clean_markdown("**Sah-AnAI**™**.**")
        assert "**Sah-AnAI™.**" in result

    def test_collapses_quad_stars(self):
        from main import _clean_markdown
        assert "****" not in _clean_markdown("### **8****.2 Impact**")


class TestMergeIntervals:
    def test_empty(self):
        from main import _merge_intervals
        assert _merge_intervals([]) == []

    def test_single(self):
        from main import _merge_intervals
        assert _merge_intervals([(1, 5)]) == [(1, 5)]

    def test_non_overlapping_sorted(self):
        from main import _merge_intervals
        assert _merge_intervals([(1, 3), (5, 8)]) == [(1, 3), (5, 8)]

    def test_overlapping_merged(self):
        from main import _merge_intervals
        assert _merge_intervals([(1, 5), (3, 8)]) == [(1, 8)]

    def test_adjacent_merged(self):
        from main import _merge_intervals
        assert _merge_intervals([(1, 5), (5, 8)]) == [(1, 8)]

    def test_unsorted_fully_merged(self):
        from main import _merge_intervals
        # (1,5), (3,12), (10,20) all overlap into (1,20)
        result = _merge_intervals([(10, 20), (1, 5), (3, 12)])
        assert result == [(1, 20)]


class TestSubtractIntervals:
    def test_no_taken(self):
        from main import _subtract_intervals
        assert _subtract_intervals([(0, 10)], []) == [(0, 10)]

    def test_fully_covered(self):
        from main import _subtract_intervals
        assert _subtract_intervals([(0, 10)], [(0, 10)]) == []

    def test_left_remainder(self):
        from main import _subtract_intervals
        assert _subtract_intervals([(0, 10)], [(5, 10)]) == [(0, 5)]

    def test_right_remainder(self):
        from main import _subtract_intervals
        assert _subtract_intervals([(0, 10)], [(0, 5)]) == [(5, 10)]

    def test_middle_punched_out(self):
        from main import _subtract_intervals
        result = _subtract_intervals([(0, 10)], [(3, 7)])
        assert result == [(0, 3), (7, 10)]

    def test_non_overlapping_taken(self):
        from main import _subtract_intervals
        assert _subtract_intervals([(0, 5)], [(10, 20)]) == [(0, 5)]


# ── Render integration test ───────────────────────────────────────────────────

class TestRenderDossierDedup:
    """Shared passage appears in the first block only; HTML/footnotes are cleaned."""

    async def test_shared_chunk_deduplicated_and_cleaned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        FULL_TEXT = (
            "Introduction paragraph.\n\n"
            "Shared passage with <b>bold HTML</b> and footnote[^1].\n\n"
            "[^1]: The footnote definition.\n\n"
            "Trailing paragraph."
        )
        shared_content = "Shared passage with <b>bold HTML</b> and footnote[^1]."
        trailing_content = "Trailing paragraph."

        assert shared_content in FULL_TEXT
        assert trailing_content in FULL_TEXT

        topic = Topic(id="t-rdd", name="T")
        db_session.add(topic)
        doc = Document(
            id="doc-rdd", topic_id="t-rdd",
            source_type=SourceType.FILE,
            source_ref="test.md",
            filename="test.md",
            minio_key="docs/test.md",
        )
        db_session.add(doc)
        await db_session.flush()

        chunk_shared = Chunk(id="ck-shared", document_id="doc-rdd", topic_id="t-rdd",
                             content=shared_content, chunk_index=0, token_count=10)
        chunk_trail = Chunk(id="ck-trail", document_id="doc-rdd", topic_id="t-rdd",
                            content=trailing_content, chunk_index=1, token_count=5)
        db_session.add_all([chunk_shared, chunk_trail])
        await db_session.flush()

        ent_a = Entity(id="ent-a", topic_id="t-rdd", name="Entity A", ref_id="ENT-000001")
        ent_b = Entity(id="ent-b", topic_id="t-rdd", name="Entity B", ref_id="ENT-000002")
        db_session.add_all([ent_a, ent_b])
        await db_session.flush()

        # Both entities share chunk_shared; only ent_b also has chunk_trail
        await db_session.execute(
            chunk_entities.insert().values([
                {"chunk_id": "ck-shared", "entity_id": "ent-a"},
                {"chunk_id": "ck-shared", "entity_id": "ent-b"},
                {"chunk_id": "ck-trail", "entity_id": "ent-b"},
            ])
        )

        dossier = Dossier(id="dos-rdd", name="Test")
        db_session.add(dossier)
        await db_session.flush()

        db_session.add_all([
            DossierBlock(id="blk-a", dossier_id="dos-rdd", block_type="entity",
                         ref_id="ent-a", order_index=0),
            DossierBlock(id="blk-b", dossier_id="dos-rdd", block_type="entity",
                         ref_id="ent-b", order_index=1),
        ])
        await db_session.commit()

        with patch("storage.download_file", new_callable=AsyncMock,
                   return_value=FULL_TEXT.encode()):
            r = await client.get("/dossiers/dos-rdd/render")

        assert r.status_code == 200
        data = r.json()

        block_a = next(b for b in data if b["block_id"] == "blk-a")
        block_b = next(b for b in data if b["block_id"] == "blk-b")

        combined_a = "\n".join(block_a["paragraphs"])
        combined_b = "\n".join(block_b["paragraphs"])

        # Shared passage only in first block
        assert "Shared passage" in combined_a
        assert "Shared passage" not in combined_b

        # Trailing content only in second block
        assert "Trailing paragraph" in combined_b
        assert "Trailing paragraph" not in combined_a

        # HTML stripped, inner text preserved
        assert "<b>" not in combined_a
        assert "bold HTML" in combined_a

        # Footnote ref stripped
        assert "[^1]" not in combined_a
        # Footnote definition line dropped
        assert "footnote definition" not in combined_a.lower()
