from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import embedder
import entifier as entifier_mod
import indexer as indexer_mod
import storage
from db import SessionLocal, create_tables, get_session, run_migrations
from models import (
    Chunk,
    ChunkSummary,
    Document,
    DocumentOut,
    Entity,
    EntityDetailOut,
    EntityIndexItem,
    EntityOut,
    EntityPatch,
    EntitySearchHit,
    Image,
    ImageOut,
    ImageSearchHit,
    IngestUrlRequest,
    Job,
    JobOut,
    JobStatus,
    SearchRequest,
    SearchResponse,
    Section,
    SectionIndexItem,
    SectionOut,
    SectionPatch,
    SmartIngestResult,
    SourceType,
    SubTopic,
    SubTopicIndexItem,
    SubTopicOut,
    SubTopicPatch,
    Topic,
    TopicCreate,
    TopicIndex,
    TopicOut,
    topic_links,
)

ALLOWED_DOC_EXTENSIONS = {".pdf", ".md", ".csv", ".json", ".yaml", ".yml"}

_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await run_migrations()
    await storage.ensure_bucket()
    await embedder.init_qdrant()
    yield


app = FastAPI(title="hermes-entifier", version="0.1.0", lifespan=lifespan)

DB = Annotated[AsyncSession, Depends(get_session)]


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Topics ────────────────────────────────────────────────────────────────────

@app.post("/topics", response_model=TopicOut, status_code=201)
async def create_topic(body: TopicCreate, db: DB):
    topic = Topic(name=body.name, description=body.description)
    db.add(topic)
    await db.commit()
    await db.refresh(topic)
    return topic


@app.get("/topics", response_model=list[TopicOut])
async def list_topics(db: DB):
    result = await db.execute(select(Topic).order_by(Topic.created_at))
    return result.scalars().all()


@app.get("/topics/{topic_id}", response_model=TopicOut)
async def get_topic(topic_id: str, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    return topic


# ── Ingest ────────────────────────────────────────────────────────────────────

async def _do_ingest_file(
    topic_id: str,
    filename: str,
    content: bytes,
    context: Optional[str],
    db: AsyncSession,
) -> Document:
    """Core file ingest logic shared by ingest_file and smart_ingest_file."""
    suffix = Path(filename).suffix.lower()

    doc = Document(
        topic_id=topic_id,
        source_type=SourceType.FILE,
        source_ref=filename,
        filename=filename,
        context=context or None,
    )
    db.add(doc)
    await db.flush()

    safe_name = Path(filename).name
    minio_key = f"{topic_id}/documents/{doc.id}/{safe_name}"
    await storage.upload_file(minio_key, content, _CONTENT_TYPES[suffix])
    doc.minio_key = minio_key

    from ingestor import parse_csv, parse_json, parse_md, parse_pdf, parse_yaml

    if suffix == ".pdf":
        text, page_count = await parse_pdf(content)
        doc.page_count = page_count
    elif suffix == ".json":
        text = parse_json(content)
    elif suffix in {".yaml", ".yml"}:
        text = parse_yaml(content)
    elif suffix == ".csv":
        text = parse_csv(content)
    else:
        text = parse_md(content)

    await db.commit()
    await db.refresh(doc)

    await _store_chunks(text, doc.id, topic_id, db, context=doc.context)
    return doc


@app.post("/topics/{topic_id}/ingest/file", response_model=DocumentOut, status_code=201)
async def ingest_file(topic_id: str, db: DB, file: UploadFile = File(...), context: Optional[str] = Form(None)):
    if context and len(context) > 1000:
        raise HTTPException(status_code=422, detail="context must be 1000 characters or fewer")
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"unsupported file type: {suffix}")

    content = await file.read()
    filename = file.filename or "unknown"
    return await _do_ingest_file(topic_id, filename, content, context, db)


MAX_SMART_INGEST_SIZE = 50 * 1024 * 1024  # 50 MB
MAX_FILES_PER_REQUEST = 20

@app.post("/smart-ingest/file", response_model=SmartIngestResult, status_code=201)
async def smart_ingest_file(db: DB, file: UploadFile = File(...), context: Optional[str] = Form(None)):
    if context and len(context) > 1000:
        raise HTTPException(status_code=422, detail="context must be 1000 characters or fewer")

    # Sanitise filename — strip any directory components from client-supplied name
    filename = Path(file.filename or "unknown").name or "unknown"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".md"}:
        raise HTTPException(status_code=422, detail=f"unsupported file type: {suffix or '(none)'}")

    content = await file.read()
    if len(content) > MAX_SMART_INGEST_SIZE:
        raise HTTPException(status_code=413, detail="file too large (max 50 MB)")

    from ingestor import parse_md, parse_pdf

    if suffix == ".pdf":
        text, _ = await parse_pdf(content)
    else:
        text = parse_md(content)
    preview = text[:1500]

    topics_result = await db.execute(select(Topic).order_by(Topic.created_at))
    all_topics = topics_result.scalars().all()
    existing_topics = [
        {"id": t.id, "name": t.name, "description": t.description}
        for t in all_topics
    ]

    import smart_classifier
    classification = await smart_classifier.classify_topic(filename, preview, existing_topics)

    topic_id: Optional[str] = None
    was_created = False

    if classification["action"] == "existing" and classification["topic_id"]:
        topic_id = classification["topic_id"]
        topic = await db.get(Topic, topic_id)
        if not topic:
            # LLM hallucinated an id — fall through to create
            classification["action"] = "new"
            topic_id = None

    if classification["action"] == "new":
        # Truncate LLM-supplied strings before storing
        topic_name = (classification.get("topic_name") or Path(filename).stem)[:200].strip()
        raw_desc = (classification.get("topic_description") or "")[:1000].strip()
        topic_description: Optional[str] = raw_desc or None

        # Avoid duplicate topics if a same-named topic was created concurrently
        existing_same = await db.execute(select(Topic).where(Topic.name == topic_name))
        existing_topic = existing_same.scalar_one_or_none()
        if existing_topic:
            topic_id = existing_topic.id
        else:
            new_topic = Topic(name=topic_name, description=topic_description)
            db.add(new_topic)
            await db.flush()
            topic_id = new_topic.id
            was_created = True

    assert topic_id is not None, "topic resolution failed"

    doc = await _do_ingest_file(topic_id, filename, content, context, db)

    topic_record = await db.get(Topic, topic_id)
    topic_name_out = topic_record.name if topic_record else topic_id

    return SmartIngestResult(
        topic_id=topic_id,
        topic_name=topic_name_out,
        was_created=was_created,
        document_id=doc.id,
        filename=filename,
    )


@app.post("/topics/{topic_id}/ingest/url", response_model=DocumentOut, status_code=201)
async def ingest_url(topic_id: str, body: IngestUrlRequest, db: DB):
    if body.context and len(body.context) > 1000:
        raise HTTPException(status_code=422, detail="context must be 1000 characters or fewer")
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    from ingestor import fetch_url

    text = await fetch_url(body.url)

    doc = Document(
        topic_id=topic_id,
        source_type=SourceType.URL,
        source_ref=body.url,
        filename="page.md",
    )
    doc.context = body.context or None
    db.add(doc)
    await db.flush()

    minio_key = f"{topic_id}/documents/{doc.id}/page.md"
    await storage.upload_file(minio_key, text.encode(), "text/markdown")
    doc.minio_key = minio_key

    await db.commit()
    await db.refresh(doc)

    await _store_chunks(text, doc.id, topic_id, db, context=doc.context)
    return doc


@app.post("/topics/{topic_id}/ingest/image", response_model=ImageOut, status_code=201)
async def ingest_image(topic_id: str, db: DB, file: UploadFile = File(...), context: Optional[str] = Form(None)):
    if context and len(context) > 1000:
        raise HTTPException(status_code=422, detail="context must be 1000 characters or fewer")
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"unsupported image type: {suffix}")

    content = await file.read()
    content_type = file.content_type or "image/png"

    img = Image(
        topic_id=topic_id,
        filename=file.filename or "image",
        file_path="",
    )
    db.add(img)
    await db.flush()

    safe_img_name = Path(file.filename or "image").name
    minio_key = f"{topic_id}/images/{img.id}/{safe_img_name}"
    await storage.upload_file(minio_key, content, content_type)
    img.minio_key = minio_key
    img.file_path = minio_key

    description = await embedder.describe_image(content, content_type)
    img.description = description or None
    embed_source = f"[User context: {context}]\n\n{description or ''}".strip() if context else description

    await db.commit()

    if embed_source:
        vectors = await embedder.embed_texts([embed_source])
        if vectors:
            await embedder.upsert_to_qdrant([
                {
                    "id": img.id,
                    "vector": vectors[0],
                    "payload": {"topic_id": topic_id, "image_id": img.id, "type": "image"},
                }
            ])
            img.qdrant_id = img.id
            await db.commit()

    await db.refresh(img)
    return img


@app.get("/topics/{topic_id}/documents", response_model=list[DocumentOut])
async def list_documents(topic_id: str, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    result = await db.execute(
        select(Document).where(Document.topic_id == topic_id).order_by(Document.created_at)
    )
    return result.scalars().all()


@app.get("/topics/{topic_id}/images", response_model=list[ImageOut])
async def list_images(topic_id: str, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    result = await db.execute(
        select(Image).where(Image.topic_id == topic_id).order_by(Image.created_at)
    )
    return result.scalars().all()


@app.get("/images/{image_id}/content")
async def get_image_content(image_id: str, db: DB):
    from fastapi.responses import Response
    img = await db.get(Image, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="image not found")
    if not img.minio_key:
        raise HTTPException(status_code=404, detail="image content not available")
    content = await storage.download_file(img.minio_key)
    suffix = Path(img.filename).suffix.lower()
    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
    return Response(content=content, media_type=media_type,
                    headers={"X-Content-Type-Options": "nosniff"})


# ── Background job runner ─────────────────────────────────────────────────────

async def _run_process_job(job_id: str, session_factory=None) -> None:
    from classifier import assign_chunks_to_subtopics, discover_subtopics

    factory = session_factory or SessionLocal
    async with factory() as db:
        job = await db.get(Job, job_id)
        if not job:
            return
        try:
            job.status = JobStatus.RUNNING
            await db.commit()

            result = await db.execute(select(Chunk).where(Chunk.topic_id == job.topic_id))
            chunks = result.scalars().all()

            if not chunks:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            subtopics = await discover_subtopics(chunks, job.topic_id, db)
            await db.commit()

            await assign_chunks_to_subtopics(chunks, subtopics, db)
            await db.commit()

            await entifier_mod.entify_all_subtopics(subtopics, job.topic_id, db)
            await db.commit()

            await indexer_mod.index_all_subtopics(subtopics, job.topic_id, db)
            await db.commit()

            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise


# ── Process job ───────────────────────────────────────────────────────────────

@app.post("/topics/{topic_id}/process", response_model=JobOut, status_code=202)
async def process_topic(topic_id: str, db: DB, background_tasks: BackgroundTasks):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    job = Job(topic_id=topic_id, type="process")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    background_tasks.add_task(_run_process_job, job.id)
    return job


@app.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: DB):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


# ── Sub-topics ────────────────────────────────────────────────────────────────

@app.get("/topics/{topic_id}/subtopics", response_model=list[SubTopicOut])
async def list_subtopics(topic_id: str, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    result = await db.execute(
        select(SubTopic).where(SubTopic.topic_id == topic_id).order_by(SubTopic.created_at)
    )
    return result.scalars().all()


@app.patch("/subtopics/{subtopic_id}", response_model=SubTopicOut)
async def patch_subtopic(subtopic_id: str, body: SubTopicPatch, db: DB):
    st = await db.get(SubTopic, subtopic_id)
    if not st:
        raise HTTPException(status_code=404, detail="subtopic not found")
    if body.name is not None:
        st.name = body.name
    if body.description is not None:
        st.description = body.description
    await db.commit()
    await db.refresh(st)
    return st


# ── Entities ──────────────────────────────────────────────────────────────────

@app.get("/topics/{topic_id}/entities", response_model=list[EntityOut])
async def list_entities(topic_id: str, db: DB, subtopic_id: Optional[str] = None):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    q = select(Entity).where(Entity.topic_id == topic_id)
    if subtopic_id:
        q = q.where(Entity.subtopic_id == subtopic_id)
    result = await db.execute(q.order_by(Entity.created_at))
    return result.scalars().all()


@app.get("/entities/{entity_id}", response_model=EntityDetailOut)
async def get_entity(entity_id: str, db: DB):
    result = await db.execute(
        select(Entity)
        .where(Entity.id == entity_id)
        .options(selectinload(Entity.chunks), selectinload(Entity.images))
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="entity not found")
    return entity


@app.patch("/entities/{entity_id}", response_model=EntityOut)
async def patch_entity(entity_id: str, body: EntityPatch, db: DB):
    entity = await db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="entity not found")
    if body.name is not None:
        entity.name = body.name
    if body.description is not None:
        entity.description = body.description
    if body.entity_type is not None:
        entity.entity_type = body.entity_type
    if body.subtopic_id is not None:
        entity.subtopic_id = body.subtopic_id
    await db.commit()
    await db.refresh(entity)
    return entity


# ── Sections ──────────────────────────────────────────────────────────────────

@app.get("/subtopics/{subtopic_id}/sections", response_model=list[SectionOut])
async def list_sections(subtopic_id: str, db: DB):
    st = await db.get(SubTopic, subtopic_id)
    if not st:
        raise HTTPException(status_code=404, detail="subtopic not found")
    result = await db.execute(
        select(Section)
        .where(Section.subtopic_id == subtopic_id)
        .order_by(Section.order_index)
    )
    return result.scalars().all()


@app.patch("/sections/{section_id}", response_model=SectionOut)
async def patch_section(section_id: str, body: SectionPatch, db: DB):
    section = await db.get(Section, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="section not found")
    if body.name is not None:
        section.name = body.name
    if body.description is not None:
        section.description = body.description
    if body.order_index is not None:
        section.order_index = body.order_index
    await db.commit()
    await db.refresh(section)
    return section


# ── Index ─────────────────────────────────────────────────────────────────────

@app.get("/topics/{topic_id}/index", response_model=TopicIndex)
async def get_topic_index(topic_id: str, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    st_result = await db.execute(
        select(SubTopic)
        .where(SubTopic.topic_id == topic_id)
        .options(
            selectinload(SubTopic.sections).selectinload(Section.entities)
        )
        .order_by(SubTopic.created_at)
    )
    subtopics = st_result.scalars().all()

    return TopicIndex(
        topic_id=topic_id,
        topic_name=topic.name,
        subtopics=[
            SubTopicIndexItem(
                id=st.id,
                name=st.name,
                description=st.description,
                sections=[
                    SectionIndexItem(
                        id=s.id,
                        name=s.name,
                        description=s.description,
                        order_index=s.order_index,
                        entities=[
                            EntityIndexItem(
                                id=e.id,
                                ref_id=e.ref_id,
                                name=e.name,
                                entity_type=e.entity_type,
                            )
                            for e in sorted(s.entities, key=lambda x: x.created_at)
                        ],
                    )
                    for s in sorted(st.sections, key=lambda x: x.order_index)
                ],
            )
            for st in subtopics
        ],
    )


# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/topics/{topic_id}/search", response_model=SearchResponse)
async def search_topic(topic_id: str, body: SearchRequest, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    from search import semantic_search

    raw = await semantic_search(topic_id, body.query, body.limit, db)

    return SearchResponse(
        entities=[
            EntitySearchHit(
                score=h["score"],
                entity=EntityOut.model_validate(h["entity"]),
                matched_excerpt=h["matched_excerpt"],
            )
            for h in raw["entities"]
        ],
        images=[
            ImageSearchHit(
                score=h["score"],
                image=ImageOut.model_validate(h["image"]),
            )
            for h in raw["images"]
        ],
    )


# ── Topic links ───────────────────────────────────────────────────────────────

@app.get("/topics/{topic_id}/links", response_model=list[TopicOut])
async def list_topic_links(topic_id: str, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    result_a = await db.execute(
        select(Topic).join(topic_links, topic_links.c.topic_id_b == Topic.id)
        .where(topic_links.c.topic_id_a == topic_id)
    )
    result_b = await db.execute(
        select(Topic).join(topic_links, topic_links.c.topic_id_a == Topic.id)
        .where(topic_links.c.topic_id_b == topic_id)
    )
    seen: set[str] = set()
    topics = []
    for t in list(result_a.scalars().all()) + list(result_b.scalars().all()):
        if t.id not in seen:
            seen.add(t.id)
            topics.append(t)
    return topics


@app.post("/topics/{topic_id}/links", response_model=TopicOut, status_code=201)
async def add_topic_link(topic_id: str, body: dict, db: DB):
    from sqlalchemy.exc import IntegrityError

    linked_id = body.get("linked_topic_id")
    if not linked_id or linked_id == topic_id:
        raise HTTPException(status_code=422, detail="invalid linked_topic_id")
    topic = await db.get(Topic, topic_id)
    linked = await db.get(Topic, linked_id)
    if not topic or not linked:
        raise HTTPException(status_code=404, detail="topic not found")

    id_a, id_b = min(topic_id, linked_id), max(topic_id, linked_id)
    existing = await db.execute(
        select(topic_links).where(
            (topic_links.c.topic_id_a == id_a) & (topic_links.c.topic_id_b == id_b)
        )
    )
    if existing.first():
        raise HTTPException(status_code=409, detail="already linked")
    try:
        await db.execute(topic_links.insert().values(topic_id_a=id_a, topic_id_b=id_b))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="already linked")
    return linked


@app.delete("/topics/{topic_id}/links/{other_id}", status_code=204)
async def remove_topic_link(topic_id: str, other_id: str, db: DB):
    id_a, id_b = min(topic_id, other_id), max(topic_id, other_id)
    await db.execute(
        topic_links.delete().where(
            (topic_links.c.topic_id_a == id_a) & (topic_links.c.topic_id_b == id_b)
        )
    )
    await db.commit()


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _store_chunks(text: str, doc_id: str, topic_id: str, db: AsyncSession, context: Optional[str] = None) -> None:
    from ingestor import chunk_text

    if context:
        text = f"[User context: {context}]\n\n{text}"

    texts = chunk_text(text)
    if not texts:
        return

    vectors = await embedder.embed_texts(texts)

    chunks = []
    for i, (chunk_text_val, vector) in enumerate(zip(texts, vectors)):
        chunk = Chunk(
            document_id=doc_id,
            topic_id=topic_id,
            content=chunk_text_val,
            chunk_index=i,
            token_count=len(chunk_text_val) // 4,
        )
        db.add(chunk)
        chunks.append((chunk, vector))

    await db.flush()

    points = [
        {
            "id": chunk.id,
            "vector": vector,
            "payload": {
                "topic_id": topic_id,
                "document_id": doc_id,
                "chunk_index": chunk.chunk_index,
                "type": "chunk",
            },
        }
        for chunk, vector in chunks
    ]
    await embedder.upsert_to_qdrant(points)

    for chunk, _ in chunks:
        chunk.qdrant_id = chunk.id

    await db.commit()
