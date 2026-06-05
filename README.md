# hermes-identify

[![CI](https://github.com/A-Souhei/hermes-identify/actions/workflows/ci.yml/badge.svg)](https://github.com/A-Souhei/hermes-identify/actions/workflows/ci.yml)

Document ingestion, classification, and entity extraction service for the hermes-docwriter plugin.

Ingest PDFs, Markdown, CSV, JSON, YAML files, URLs, and images — the service classifies them into sub-topics, extracts named entities, groups them into document sections, and exposes everything via a REST API.

## Stack

| Service | Role | External port |
|---|---|---|
| `entifier` | FastAPI core API | 37491 |
| `postgres` | Metadata storage | 25432 |
| `qdrant` | Vector embeddings | 26333 |
| `minio` | Blob storage (files + images) | 39000 / 39001 |

## Quick start

```bash
cp .env.example .env
# fill in OPENAI_API_KEY and FIRECRAWL_URL
docker compose up -d
```

API is available at `http://localhost:37491`. No authentication.

## Pipeline

`POST /topics/{id}/process` runs the full pipeline asynchronously:

1. **Chunk** — split documents into ~800-token overlapping chunks, embed images via vision LLM
2. **Embed** — OpenAI `text-embedding-3-small` → store in Qdrant
3. **Classify** — LLM discovers 3–12 sub-topics, assigns each chunk to 1–2 sub-topics
4. **Entify** — LLM extracts named entities per sub-topic (`ENT-xxxxxx` ref IDs)
5. **Index** — LLM groups entities into ordered sections per sub-topic
6. **Done** — poll `GET /jobs/{id}` for status

## Key endpoints

```
POST   /topics                          create topic
POST   /topics/{id}/ingest/file         upload PDF, MD, CSV, JSON, or YAML
POST   /topics/{id}/ingest/url          crawl URL via Firecrawl
POST   /topics/{id}/ingest/image        upload image (PNG/JPG/WEBP/GIF)
POST   /topics/{id}/process             run full pipeline → job_id
GET    /jobs/{id}                       job status
GET    /topics/{id}/index               full nested outline (subtopic → section → entity)
POST   /topics/{id}/search              semantic search over entities + images
GET    /topics/{id}/subtopics           list sub-topics
GET    /subtopics/{id}/sections         list sections
GET    /topics/{id}/entities            list entities (filterable by ?subtopic_id=)
GET    /entities/{id}                   entity detail + linked chunks + images
PATCH  /entities/{id}                   rename / retype / reassign
PATCH  /subtopics/{id}                  rename sub-topic
PATCH  /sections/{id}                   rename / reorder section
```

## Configuration

See `.env.example`. Key variables:

```
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint
FIRECRAWL_URL=http://your-firecrawl:PORT    # self-hosted, no auth required
```

The entifier can run on a separate server from hermes-docwriter — point the plugin at it via `ENTIFIER_URL`.

## Tests

```bash
cd services/entifier
python -m pytest tests/ -v   # 82 tests, all external services mocked
```

## License

MIT
