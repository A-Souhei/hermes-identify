from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import embedder
import storage
from db import create_tables, get_session
from models import (
    Chunk,
    Document,
    DocumentOut,
    Image,
    ImageOut,
    IngestUrlRequest,
    SourceType,
    Topic,
    TopicCreate,
    TopicOut,
)

ALLOWED_DOC_EXTENSIONS = {".pdf", ".md"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
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

@app.post("/topics/{topic_id}/ingest/file", response_model=DocumentOut, status_code=201)
async def ingest_file(topic_id: str, db: DB, file: UploadFile = File(...)):
    topic = await db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"unsupported file type: {suffix}")

    content = await file.read()

    doc = Document(
        topic_id=topic_id,
        source_type=SourceType.FILE,
        source_ref=file.filename or "unknown",
        filename=file.filename,
    )
    db.add(doc)
    await db.flush()

    minio_key = f"{topic_id}/documents/{doc.id}/{file.filename}"
    content_type = "application/pdf" if suffix == ".pdf" else "text/markdown"
    await storage.upload_file(minio_key, content, content_type)
    doc.minio_key = minio_key

    from ingestor import chunk_text, parse_md, parse_pdf

    if suffix == ".pdf":
        text, page_count = await parse_pdf(content)
        doc.page_count = page_count
    else:
        text = parse_md(content)

    await db.commit()
    await db.refresh(doc)

    await _store_chunks(text, doc.id, topic_id, db)
    return doc


@app.post("/topics/{topic_id}/ingest/url", response_model=DocumentOut, status_code=201)
async def ingest_url(topic_id: str, body: IngestUrlRequest, db: DB):
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
    db.add(doc)
    await db.flush()

    minio_key = f"{topic_id}/documents/{doc.id}/page.md"
    await storage.upload_file(minio_key, text.encode(), "text/markdown")
    doc.minio_key = minio_key

    await db.commit()
    await db.refresh(doc)

    await _store_chunks(text, doc.id, topic_id, db)
    return doc


@app.post("/topics/{topic_id}/ingest/image", response_model=ImageOut, status_code=201)
async def ingest_image(topic_id: str, db: DB, file: UploadFile = File(...)):
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

    minio_key = f"{topic_id}/images/{img.id}/{file.filename}"
    await storage.upload_file(minio_key, content, content_type)
    img.minio_key = minio_key
    img.file_path = minio_key

    description = await embedder.describe_image(content, content_type)
    img.description = description

    await db.commit()
    await db.flush()

    if description:
        vectors = await embedder.embed_texts([description])
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


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _store_chunks(text: str, doc_id: str, topic_id: str, db: AsyncSession) -> None:
    from ingestor import chunk_text

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
