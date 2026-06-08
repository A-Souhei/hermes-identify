from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import embedder
import entifier as entifier_mod
import indexer as indexer_mod
import storage
from db import SessionLocal, create_tables, get_session, run_migrations
from models import (
    _now,
    Chunk,
    ChunkSummary,
    chunk_entities,
    chunk_subtopics,
    Document,
    DocumentOut,
    Dossier,
    DossierBlock,
    DossierBlockCreate,
    DossierBlockPatch,
    DossierBlockResolved,
    DossierBlocksReorder,
    DossierCreate,
    DossierDetail,
    DossierOut,
    DossierPatch,
    DossierRenderBlock,
    Entity,
    EntityDetailOut,
    EntityIndexItem,
    EntityOut,
    EntityPatch,
    EntitySearchHit,
    Image,
    image_entities,
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
async def ingest_image(topic_id: str, db: DB, file: UploadFile = File(...), context: str = Form(...)):
    context = context.strip()
    if not context:
        raise HTTPException(status_code=422, detail="context is required")
    if len(context) > 5000:
        raise HTTPException(status_code=422, detail="context must be 5000 characters or fewer")
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
        description=context,
    )
    db.add(img)
    await db.flush()

    safe_img_name = Path(file.filename or "image").name
    minio_key = f"{topic_id}/images/{img.id}/{safe_img_name}"
    await storage.upload_file(minio_key, content, content_type)
    img.minio_key = minio_key
    img.file_path = minio_key

    ai_description = await embedder.describe_image(content, content_type)
    embed_source = f"{context}\n\n{ai_description or ''}".strip()

    # Ingest context text as a searchable document
    doc = Document(
        topic_id=topic_id,
        source_type=SourceType.FILE,
        source_ref=img.id,
        filename=safe_img_name,
        context=context,
    )
    db.add(doc)
    await db.flush()

    doc_key = f"{topic_id}/documents/{doc.id}/{safe_img_name}.md"
    await storage.upload_file(doc_key, context.encode(), "text/markdown")
    doc.minio_key = doc_key

    await db.commit()

    await _store_chunks(context, doc.id, topic_id, db)

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

async def _clear_topic_derived_data(topic_id: str, db: AsyncSession) -> None:
    """Remove derived artifacts (subtopics, sections, entities and their
    association rows) for a topic so a re-process rebuilds cleanly instead of
    appending duplicates. Source data (documents, chunks, images) is preserved;
    none of these artifacts live in Qdrant, so no vector cleanup is needed.
    """
    entity_ids = select(Entity.id).where(Entity.topic_id == topic_id)
    subtopic_ids = select(SubTopic.id).where(SubTopic.topic_id == topic_id)

    # Association tables have no ON DELETE CASCADE, so clear their rows first.
    await db.execute(delete(chunk_entities).where(chunk_entities.c.entity_id.in_(entity_ids)))
    await db.execute(delete(image_entities).where(image_entities.c.entity_id.in_(entity_ids)))
    await db.execute(delete(chunk_subtopics).where(chunk_subtopics.c.subtopic_id.in_(subtopic_ids)))

    # Entities reference subtopics and sections, so delete them before those.
    await db.execute(delete(Entity).where(Entity.topic_id == topic_id))
    await db.execute(delete(Section).where(Section.topic_id == topic_id))
    await db.execute(delete(SubTopic).where(SubTopic.topic_id == topic_id))


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

            # Re-processing rebuilds from scratch: drop prior subtopics,
            # sections and entities so they aren't duplicated.
            await _clear_topic_derived_data(job.topic_id, db)
            await db.commit()

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
    existing = await db.execute(
        select(Job).where(
            Job.topic_id == topic_id,
            Job.type == "process",
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
    )
    in_flight = existing.scalar_one_or_none()
    if in_flight is not None:
        return in_flight
    job = Job(topic_id=topic_id, type="process")
    db.add(job)
    await db.commit()
    await db.refresh(job)
    background_tasks.add_task(_run_process_job, job.id)
    return job


@app.get("/topics/{topic_id}/active-job", response_model=Optional[JobOut])
async def get_active_job(topic_id: str, db: DB):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    result = await db.execute(
        select(Job)
        .where(
            Job.topic_id == topic_id,
            Job.type == "process",
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
        )
        .order_by(Job.created_at.desc())
    )
    return result.scalars().first()


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
    result = await db.execute(q.options(selectinload(Entity.images)).order_by(Entity.created_at))
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
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id).options(selectinload(Entity.images))
    )
    updated = result.scalar_one_or_none()
    if not updated:
        raise HTTPException(status_code=404, detail="entity not found")
    return updated


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
            selectinload(SubTopic.sections).selectinload(Section.entities).selectinload(Entity.images)
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
                                with_image=bool(e.images),
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


# ── Dossiers ──────────────────────────────────────────────────────────────────

_VALID_BLOCK_TYPES = {"subtopic", "section", "entity", "image"}


async def _resolve_block(block: DossierBlock, db: AsyncSession) -> DossierBlockResolved:
    bt = block.block_type
    ref_id = block.ref_id
    label = "(deleted)"
    meta: dict = {}

    if bt == "subtopic":
        obj = await db.get(SubTopic, ref_id)
        if obj:
            label = obj.name
            meta = {"description": obj.description, "topic_id": obj.topic_id}
    elif bt == "section":
        obj = await db.get(Section, ref_id)
        if obj:
            label = obj.name
            meta = {
                "description": obj.description,
                "subtopic_id": obj.subtopic_id,
                "topic_id": obj.topic_id,
                "order_index": obj.order_index,
            }
    elif bt == "entity":
        ent_result = await db.execute(
            select(Entity).where(Entity.id == ref_id).options(selectinload(Entity.images))
        )
        obj = ent_result.scalar_one_or_none()
        if obj:
            label = obj.name
            meta = {
                "description": obj.description,
                "entity_type": obj.entity_type.value if obj.entity_type is not None else None,
                "subtopic_id": obj.subtopic_id,
                "section_id": obj.section_id,
                "with_image": bool(obj.images),
            }
    elif bt == "image":
        obj = await db.get(Image, ref_id)
        if obj:
            label = obj.filename
            meta = {"description": obj.description, "minio_key": obj.minio_key}

    return DossierBlockResolved(
        id=block.id,
        block_type=bt,
        ref_id=ref_id,
        order_index=block.order_index,
        label=label,
        meta=meta,
    )


@app.get("/dossiers", response_model=list[DossierOut])
async def list_dossiers(db: DB):
    result = await db.execute(select(Dossier).order_by(Dossier.created_at.desc()))
    return result.scalars().all()


@app.post("/dossiers", response_model=DossierOut, status_code=201)
async def create_dossier(body: DossierCreate, db: DB):
    dossier = Dossier(name=body.name)
    db.add(dossier)
    await db.commit()
    await db.refresh(dossier)
    return dossier


@app.get("/dossiers/{dossier_id}", response_model=DossierDetail)
async def get_dossier(dossier_id: str, db: DB):
    result = await db.execute(
        select(Dossier)
        .where(Dossier.id == dossier_id)
        .options(selectinload(Dossier.blocks))
    )
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise HTTPException(status_code=404, detail="dossier not found")
    blocks = [await _resolve_block(b, db) for b in dossier.blocks]
    return DossierDetail(
        id=dossier.id,
        name=dossier.name,
        created_at=dossier.created_at,
        updated_at=dossier.updated_at,
        blocks=blocks,
    )


# ── Dossier render helpers ────────────────────────────────────────────────────

import re as _re


async def _document_full_text(doc: Document, cache: dict) -> str:
    """Download and parse a document's raw bytes into plain text, cached by doc.id."""
    if doc.id in cache:
        return cache[doc.id]
    try:
        if not doc.minio_key:
            raise ValueError("no minio_key")
        content: bytes = await storage.download_file(doc.minio_key)
        suffix = Path(doc.filename or "").suffix.lower() if doc.filename else ""
        if suffix == ".pdf":
            from ingestor import parse_pdf
            text, _ = await parse_pdf(content)
        elif suffix == ".csv":
            from ingestor import parse_csv
            text = parse_csv(content)
        elif suffix == ".json":
            from ingestor import parse_json
            text = parse_json(content)
        elif suffix in (".yaml", ".yml"):
            from ingestor import parse_yaml
            text = parse_yaml(content)
        else:
            from ingestor import parse_md
            text = parse_md(content)
    except Exception:
        text = ""
    cache[doc.id] = text
    return text


def _chunk_offsets(full_text: str, chunks_ordered: list) -> dict:
    """Map each chunk id to its (start, end) byte offsets in full_text."""
    offsets: dict = {}
    cursor = 0
    for chunk in sorted(chunks_ordered, key=lambda c: c.chunk_index):
        pos = full_text.find(chunk.content, cursor)
        if pos == -1:
            pos = full_text.find(chunk.content)
        if pos == -1:
            continue
        offsets[chunk.id] = (pos, pos + len(chunk.content))
        cursor = pos + 1
    return offsets


def _merge_intervals(intervals: list) -> list:
    """Merge overlapping/adjacent intervals into sorted non-overlapping list."""
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    merged = [sorted_iv[0]]
    for s, e in sorted_iv[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _subtract_intervals(targets: list, taken: list) -> list:
    """Return the regions in targets that don't overlap with taken."""
    if not taken:
        return targets
    result = []
    for ts, te in targets:
        remaining = [(ts, te)]
        for rs, re_ in taken:
            new_remaining = []
            for s, e in remaining:
                if re_ <= s or rs >= e:
                    new_remaining.append((s, e))
                else:
                    if s < rs:
                        new_remaining.append((s, rs))
                    if re_ < e:
                        new_remaining.append((re_, e))
            remaining = new_remaining
        result.extend(remaining)
    return result


_TABLE_RE = _re.compile(r'<table\b[^>]*>.*?</table>', _re.DOTALL | _re.IGNORECASE)
_FOOTNOTE_REF_RE = _re.compile(r'\[\^[^\]]+\]')
_FOOTNOTE_DEF_RE = _re.compile(r'^\[\^[^\]]+\]:.*$', _re.MULTILINE)
_HTML_TAG_RE = _re.compile(r'<[^>]+>')
# Merge bold runs split by a removed inline tag, e.g. "**A**™**.**" -> "**A™.**"
_BOLD_MERGE_RE = _re.compile(r'\*\*([^*]+?)\*\*([^\s*]{1,3})\*\*([^*]+?)\*\*')
_QUAD_STAR_RE = _re.compile(r'\*{4,}')
_DOUBLE_DOT_RE = _re.compile(r'(?<!\.)\.\.(?!\.)')
_MULTI_NEWLINE_RE = _re.compile(r'\n{3,}')
# A line made up entirely of markdown-structural punctuation (e.g. ">***", "***", "---").
_ARTIFACT_LINE_RE = _re.compile(r'[>*_~.\-`|\s]+')
# A heading line: ATX ("## Title") or a fully bold-italic pseudo-heading ("***Title***").
_HEADING_LINE_RE = _re.compile(r'#{1,6}\s+\S.*|\*{3}.+\*{3}')


def _snap_to_paragraph(full_text: str, start: int, end: int) -> tuple:
    """Expand an offset range outward to the nearest blank-line boundaries so
    excerpts begin and end at paragraph breaks instead of mid-sentence."""
    para_start = full_text.rfind("\n\n", 0, start)
    start = 0 if para_start == -1 else para_start + 2
    para_end = full_text.find("\n\n", end)
    end = len(full_text) if para_end == -1 else para_end
    return start, end


def _trim_partial_tables(start: int, end: int, tables: list) -> tuple:
    """If the span begins or ends inside an HTML table, pull the boundary out of
    it so excerpts never include orphaned table-cell fragments (the wrapping
    <table> tags lie outside the slice and so escape _clean_markdown)."""
    for ts, te in tables:
        if ts <= start < te:
            start = te
        if ts < end <= te:
            end = ts
    return start, end


def _clean_markdown(text: str) -> str:
    """Reduce raw source markdown to clean flowing prose: drop layout tables and
    footnotes, strip inline HTML, repair bold runs broken by tag removal, and
    discard punctuation-only artifact lines."""
    text = _TABLE_RE.sub('\n\n', text)            # drop layout/callout tables wholesale
    text = _FOOTNOTE_DEF_RE.sub('', text)
    text = _FOOTNOTE_REF_RE.sub('', text)
    text = _HTML_TAG_RE.sub('', text)             # keep inner text of remaining inline tags
    for _ in range(2):
        text = _BOLD_MERGE_RE.sub(r'**\1\2\3**', text)
    text = _QUAD_STAR_RE.sub('', text)            # collapse "****" emphasis noise
    text = _DOUBLE_DOT_RE.sub('.', text)
    # Drop lines that are nothing but markdown-structural punctuation (">***", "***").
    lines = [
        ln for ln in text.split('\n')
        if not ln.strip() or not _ARTIFACT_LINE_RE.fullmatch(ln.strip())
    ]
    # Drop trailing headings with no body text after them (dangling section titles
    # left behind when their table/body was removed).
    while lines:
        last = lines[-1].strip()
        if not last or _HEADING_LINE_RE.fullmatch(last):
            lines.pop()
        else:
            break
    text = '\n'.join(lines)
    text = _MULTI_NEWLINE_RE.sub('\n\n', text)
    return text.strip()


@app.get("/dossiers/{dossier_id}/render", response_model=list[DossierRenderBlock])
async def render_dossier(dossier_id: str, db: DB):
    result = await db.execute(
        select(Dossier).where(Dossier.id == dossier_id).options(selectinload(Dossier.blocks))
    )
    dossier = result.scalar_one_or_none()
    if not dossier:
        raise HTTPException(status_code=404, detail="dossier not found")

    text_cache: dict = {}
    # emitted[doc_id] = merged list of (start, end) intervals already output
    emitted: dict = {}

    rendered: list[DossierRenderBlock] = []
    for block in sorted(dossier.blocks, key=lambda b: b.order_index):
        bt = block.block_type
        ref = block.ref_id

        if bt == "image":
            obj = await db.get(Image, ref)
            rendered.append(DossierRenderBlock(
                block_id=block.id, block_type=bt,
                label=obj.filename if obj else "(deleted)",
                paragraphs=[_clean_markdown(obj.description)] if obj and obj.description else [],
                image_id=ref if obj else None,
            ))
            continue

        # Resolve chunks for this block
        block_chunks: list = []
        label = "(deleted)"

        if bt == "subtopic":
            st_res = await db.execute(
                select(SubTopic).where(SubTopic.id == ref).options(selectinload(SubTopic.chunks))
            )
            obj = st_res.scalar_one_or_none()
            if obj:
                label = obj.name
                block_chunks = list(obj.chunks)

        elif bt == "section":
            sec_res = await db.execute(
                select(Section).where(Section.id == ref).options(
                    selectinload(Section.entities).selectinload(Entity.chunks)
                )
            )
            obj = sec_res.scalar_one_or_none()
            if obj:
                label = obj.name
                for ent in obj.entities:
                    block_chunks.extend(ent.chunks)

        elif bt == "entity":
            ent_res = await db.execute(
                select(Entity).where(Entity.id == ref).options(selectinload(Entity.chunks))
            )
            obj = ent_res.scalar_one_or_none()
            if obj:
                label = obj.name
                block_chunks = list(obj.chunks)

        # Group chunks by document
        chunks_by_doc: dict = {}
        for chunk in block_chunks:
            chunks_by_doc.setdefault(chunk.document_id, []).append(chunk)

        paragraphs: list[str] = []
        seen_chunk_ids: set = set()  # for fallback dedup

        for doc_id, doc_chunks in chunks_by_doc.items():
            # Fetch the document to get created_at for ordering
            doc = await db.get(Document, doc_id)
            if doc is None:
                continue

            full_text = await _document_full_text(doc, text_cache)

            if not full_text:
                # Fallback: emit raw chunk content, deduped by chunk id
                for chunk in sorted(doc_chunks, key=lambda c: c.chunk_index):
                    if chunk.id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk.id)
                        cleaned = _clean_markdown(chunk.content)
                        if cleaned:
                            paragraphs.append(cleaned)
                continue

            offsets = _chunk_offsets(full_text, doc_chunks)
            if not offsets:
                continue

            # Coherent excerpt: one contiguous span from the block's earliest to
            # latest chunk, snapped to paragraph boundaries and pulled clear of any
            # partial table, instead of stitching scattered fragments.
            iv = list(offsets.values())
            tables = [(m.start(), m.end()) for m in _TABLE_RE.finditer(full_text)]
            s0, e0 = _snap_to_paragraph(full_text, min(s for s, _ in iv), max(e for _, e in iv))
            s0, e0 = _trim_partial_tables(s0, e0, tables)
            if s0 >= e0:
                continue
            span = (s0, e0)

            already_emitted = emitted.get(doc_id, [])
            new_intervals = _subtract_intervals([span], already_emitted)

            for s, e in sorted(new_intervals, key=lambda x: x[0]):
                cleaned = _clean_markdown(full_text[s:e])
                if cleaned:
                    paragraphs.append(cleaned)

            if new_intervals:
                emitted[doc_id] = _merge_intervals(already_emitted + new_intervals)

        # Always emit heading blocks (subtopic/section) even if empty
        if bt == "entity" and not paragraphs:
            continue

        rendered.append(DossierRenderBlock(
            block_id=block.id, block_type=bt,
            label=label,
            paragraphs=paragraphs,
        ))

    return rendered


@app.patch("/dossiers/{dossier_id}", response_model=DossierOut)
async def patch_dossier(dossier_id: str, body: DossierPatch, db: DB):
    dossier = await db.get(Dossier, dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="dossier not found")
    if body.name is not None:
        dossier.name = body.name
    dossier.updated_at = _now()
    await db.commit()
    await db.refresh(dossier)
    return dossier


@app.delete("/dossiers/{dossier_id}", status_code=204)
async def delete_dossier(dossier_id: str, db: DB):
    dossier = await db.get(Dossier, dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="dossier not found")
    await db.delete(dossier)
    await db.commit()


@app.post("/dossiers/{dossier_id}/blocks", response_model=DossierBlockResolved, status_code=201)
async def add_dossier_block(dossier_id: str, body: DossierBlockCreate, db: DB):
    if body.block_type not in _VALID_BLOCK_TYPES:
        raise HTTPException(status_code=422, detail=f"block_type must be one of {sorted(_VALID_BLOCK_TYPES)}")
    dossier = await db.get(Dossier, dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="dossier not found")
    existing = await db.execute(
        select(DossierBlock).where(
            DossierBlock.dossier_id == dossier_id,
            DossierBlock.ref_id == body.ref_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="element already in dossier")
    block = DossierBlock(
        dossier_id=dossier_id,
        block_type=body.block_type,
        ref_id=body.ref_id,
        order_index=body.order_index,
    )
    db.add(block)
    dossier.updated_at = _now()
    await db.commit()
    await db.refresh(block)
    return await _resolve_block(block, db)


@app.delete("/dossiers/{dossier_id}/blocks/{block_id}", status_code=204)
async def remove_dossier_block(dossier_id: str, block_id: str, db: DB):
    block = await db.get(DossierBlock, block_id)
    if not block or block.dossier_id != dossier_id:
        raise HTTPException(status_code=404, detail="block not found")
    dossier = await db.get(Dossier, dossier_id)
    if dossier:
        dossier.updated_at = _now()
    await db.delete(block)
    await db.commit()


@app.patch("/dossiers/{dossier_id}/blocks/reorder", status_code=204)
async def reorder_dossier_blocks(dossier_id: str, body: DossierBlocksReorder, db: DB):
    dossier = await db.get(Dossier, dossier_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="dossier not found")

    result = await db.execute(
        select(DossierBlock).where(DossierBlock.dossier_id == dossier_id)
    )
    existing = {b.id: b for b in result.scalars().all()}

    if len(body.block_ids) != len(existing) or set(body.block_ids) != set(existing.keys()):
        raise HTTPException(status_code=422, detail="block_ids must contain exactly all blocks in this dossier")

    for i, bid in enumerate(body.block_ids):
        existing[bid].order_index = i

    dossier.updated_at = _now()
    await db.commit()


@app.patch("/dossiers/{dossier_id}/blocks/{block_id}", response_model=DossierBlockResolved)
async def patch_dossier_block(dossier_id: str, block_id: str, body: DossierBlockPatch, db: DB):
    block = await db.get(DossierBlock, block_id)
    if not block or block.dossier_id != dossier_id:
        raise HTTPException(status_code=404, detail="block not found")
    block.order_index = body.order_index
    dossier = await db.get(Dossier, dossier_id)
    if dossier:
        dossier.updated_at = _now()
    await db.commit()
    await db.refresh(block)
    return await _resolve_block(block, db)
