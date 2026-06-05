"""
Phase G -- end-to-end tests against the live Docker stack.
Run with: pytest tests/ -m e2e -v
Requires: docker compose up -d and a real OPENAI_API_KEY in .env
"""
import asyncio
import os
import time

import httpx
import pytest

pytestmark = pytest.mark.e2e

BASE_URL = os.getenv("ENTIFIER_URL", "http://localhost:37491")
POLL_INTERVAL = 5    # seconds between job status checks
POLL_TIMEOUT  = 180  # seconds before giving up

DOC_SOLAR = (
    "# Solar Energy Overview\n\n"
    "Solar energy is radiant light and heat from the sun harnessed via photovoltaics,\n"
    "solar thermal energy, and solar architecture.\n\n"
    "## Photovoltaic Technology\n\n"
    "Photovoltaic (PV) cells convert sunlight directly into electricity using semiconductor\n"
    "materials, primarily silicon. Commercial panel efficiency ranges from 15% to 22%.\n"
    "Monocrystalline cells offer the highest efficiency; polycrystalline and thin-film\n"
    "variants trade efficiency for lower manufacturing cost.\n\n"
    "## Concentrated Solar Power\n\n"
    "CSP plants use mirrors or lenses to focus sunlight onto a receiver, generating heat\n"
    "that drives a steam turbine. Molten salt storage allows CSP plants to deliver power\n"
    "after sunset, distinguishing them from PV-only installations.\n\n"
    "## Global Deployment\n\n"
    "Global installed solar capacity exceeded 1,500 GW in 2025. China leads with approx 600 GW,\n"
    "followed by the EU and the United States. The levelised cost of solar electricity\n"
    "fell more than 90% between 2010 and 2024, making it the cheapest source of new\n"
    "electricity generation in most markets.\n"
).encode()

DOC_WIND = (
    "# Wind Energy Fundamentals\n\n"
    "Wind turbines convert kinetic energy from moving air into electricity via a rotor,\n"
    "gearbox (or direct-drive), and generator.\n\n"
    "## Onshore Wind\n\n"
    "Onshore turbines range from 2 MW to 6 MW. They are the most cost-competitive source\n"
    "of new generation in many regions. Key siting constraints include noise, visual impact,\n"
    "and proximity to transmission infrastructure.\n\n"
    "## Offshore Wind\n\n"
    "Offshore turbines now reach 12-15 MW capacity and benefit from stronger, steadier\n"
    "winds. Capacity factors of 40-60% compare favourably with the 25-35% typical onshore.\n"
    "Floating offshore wind is emerging for water depths beyond 60 m.\n\n"
    "## Grid Integration\n\n"
    "Wind variability is managed through geographic diversification, battery and pumped-hydro\n"
    "storage, demand-response programmes, and high-voltage DC interconnectors that link\n"
    "regional grids.\n\n"
    "## Industry Leaders\n\n"
    "Vestas, Siemens Gamesa, and GE Vernova dominate turbine manufacturing. Orsted, RWE,\n"
    "and Equinor are the largest offshore wind developers by installed capacity.\n"
).encode()

DOC_STORAGE = (
    "# Energy Storage Technologies\n\n"
    "Storage is the key enabler for a high-renewable power system, smoothing the\n"
    "mismatch between variable generation and demand.\n\n"
    "## Lithium-Ion Batteries\n\n"
    "Li-ion dominates grid-scale short-duration storage (2-4 hours). Pack costs fell\n"
    "from $1,200/kWh in 2010 to below $140/kWh in 2024. Co-located solar-plus-storage\n"
    "projects are now the fastest-growing segment of new capacity additions.\n\n"
    "## Long-Duration Storage\n\n"
    "- Pumped hydro: Accounts for approx 90% of global storage capacity. Requires suitable\n"
    "  geography but offers low cost per kWh and multi-decade asset life.\n"
    "- Flow batteries: Vanadium redox and iron-air technologies suit 8-12 hour durations.\n"
    "- Green hydrogen: Surplus renewable electricity drives electrolysis; hydrogen is\n"
    "  stored as gas, liquid, or ammonia and reconverted via fuel cells or turbines.\n\n"
    "## Market Outlook\n\n"
    "Global battery storage installations surpassed 100 GW in 2024. Rapidly falling costs\n"
    "and policy mandates are accelerating deployment across the US, China, and Europe.\n"
).encode()


@pytest.mark.e2e
class TestEndToEnd:
    """Full pipeline smoke-test: ingest -> process -> validate -> search."""

    async def test_full_pipeline(self):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
            # 1. Health check
            r = await client.get("/health")
            assert r.status_code == 200, f"Service not reachable: {r.text}"

            # 2. Create topic
            r = await client.post(
                "/topics",
                json={
                    "name": "Renewable Energy",
                    "description": "Solar, wind and storage technologies",
                },
            )
            assert r.status_code == 201
            tid = r.json()["id"]

            # 3. Ingest three markdown documents
            for filename, content in [
                ("solar.md", DOC_SOLAR),
                ("wind.md", DOC_WIND),
                ("storage.md", DOC_STORAGE),
            ]:
                r = await client.post(
                    f"/topics/{tid}/ingest/file",
                    files={"file": (filename, content, "text/markdown")},
                )
                assert r.status_code == 201, f"Ingest {filename} failed: {r.text}"

            # 4. Verify documents are listed
            r = await client.get(f"/topics/{tid}/documents")
            assert r.status_code == 200
            assert len(r.json()) == 3

            # 5. Start the pipeline
            r = await client.post(f"/topics/{tid}/process")
            assert r.status_code == 202, f"Process start failed: {r.text}"
            job_id = r.json()["id"]

            # 6. Poll until complete (real LLM calls -- allow up to POLL_TIMEOUT seconds)
            deadline = time.monotonic() + POLL_TIMEOUT
            job_status = None
            while time.monotonic() < deadline:
                r = await client.get(f"/jobs/{job_id}")
                assert r.status_code == 200
                job_status = r.json()["status"]
                if job_status in ("completed", "failed"):
                    break
                await asyncio.sleep(POLL_INTERVAL)

            assert job_status == "completed", (
                f"Job ended with status={job_status}. "
                "Check logs: docker compose logs entifier"
            )

            # 7. Subtopics were discovered
            r = await client.get(f"/topics/{tid}/subtopics")
            assert r.status_code == 200
            subtopics = r.json()
            assert len(subtopics) >= 1, "Expected at least one sub-topic"

            # 8. Entities extracted with correct ref_id format
            r = await client.get(f"/topics/{tid}/entities")
            assert r.status_code == 200
            entities = r.json()
            assert len(entities) >= 1, "Expected at least one entity"
            assert all(e["ref_id"].startswith("ENT-") for e in entities), \
                "All entities must have ENT-xxxxxx ref_id"

            # 9. Index has at least one section
            r = await client.get(f"/topics/{tid}/index")
            assert r.status_code == 200
            index = r.json()
            assert len(index["subtopics"]) >= 1
            total_sections = sum(len(st["sections"]) for st in index["subtopics"])
            assert total_sections >= 1, "Expected at least one section in the index"

            # 10. Semantic search returns entity hits
            r = await client.post(
                f"/topics/{tid}/search",
                json={"query": "solar panel efficiency and cost reduction", "limit": 5},
            )
            assert r.status_code == 200
            results = r.json()
            assert "entities" in results
            assert "images" in results
            assert len(results["entities"]) >= 1, "Search should return at least one entity hit"
