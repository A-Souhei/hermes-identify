import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pydantic import BaseModel, ConfigDict, Field

from db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


chunk_entities = Table(
    "chunk_entities",
    Base.metadata,
    Column("chunk_id", String, ForeignKey("chunks.id"), primary_key=True),
    Column("entity_id", String, ForeignKey("entities.id"), primary_key=True),
)

image_entities = Table(
    "image_entities",
    Base.metadata,
    Column("image_id", String, ForeignKey("images.id"), primary_key=True),
    Column("entity_id", String, ForeignKey("entities.id"), primary_key=True),
)

chunk_subtopics = Table(
    "chunk_subtopics",
    Base.metadata,
    Column("chunk_id", String, ForeignKey("chunks.id"), primary_key=True),
    Column("subtopic_id", String, ForeignKey("subtopics.id"), primary_key=True),
)

topic_links = Table(
    "topic_links",
    Base.metadata,
    Column("topic_id_a", String, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id_b", String, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
)


class SourceType(PyEnum):
    FILE = "file"
    URL = "url"


class JobStatus(PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EntityType(PyEnum):
    CONCEPT = "concept"
    METHODOLOGY = "methodology"
    DATA_SOURCE = "data_source"
    CASE_STUDY = "case_study"
    FINDING = "finding"
    FRAMEWORK = "framework"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    documents: Mapped[list["Document"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    images: Mapped[list["Image"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    subtopics: Mapped[list["SubTopic"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    entities: Mapped[list["Entity"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    sections: Mapped[list["Section"]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    linked_topics: Mapped[list["Topic"]] = relationship(
        "Topic",
        secondary=topic_links,
        primaryjoin="Topic.id == topic_links.c.topic_id_a",
        secondaryjoin="Topic.id == topic_links.c.topic_id_b",
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("topics.id"), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[Optional[str]] = mapped_column(String)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)
    minio_key: Mapped[Optional[str]] = mapped_column(String)
    context: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    document_id: Mapped[str] = mapped_column(String, ForeignKey("documents.id"), nullable=False)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("topics.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    qdrant_id: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped["Document"] = relationship(back_populates="chunks")
    entities: Mapped[list["Entity"]] = relationship(secondary=chunk_entities, back_populates="chunks")
    subtopics: Mapped[list["SubTopic"]] = relationship(secondary=chunk_subtopics, back_populates="chunks")


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("topics.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    qdrant_id: Mapped[Optional[str]] = mapped_column(String)
    minio_key: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="images")
    entities: Mapped[list["Entity"]] = relationship(secondary=image_entities, back_populates="images")


class SubTopic(Base):
    __tablename__ = "subtopics"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("topics.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    keywords: Mapped[Optional[str]] = mapped_column(Text)  # JSON array stored as text
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="subtopics")
    entities: Mapped[list["Entity"]] = relationship(back_populates="subtopic")
    chunks: Mapped[list["Chunk"]] = relationship(secondary=chunk_subtopics, back_populates="subtopics")
    sections: Mapped[list["Section"]] = relationship(back_populates="subtopic", cascade="all, delete-orphan")


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("topics.id"), nullable=False)
    subtopic_id: Mapped[str] = mapped_column(String, ForeignKey("subtopics.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="sections")
    subtopic: Mapped["SubTopic"] = relationship(back_populates="sections")
    entities: Mapped[list["Entity"]] = relationship(back_populates="section")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("topics.id"), nullable=False)
    subtopic_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("subtopics.id"))
    section_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("sections.id"))
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    entity_type: Mapped[Optional[EntityType]] = mapped_column(Enum(EntityType))
    ref_id: Mapped[str] = mapped_column(String, nullable=False)  # ENT-xxxxxx
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    topic: Mapped["Topic"] = relationship(back_populates="entities")
    subtopic: Mapped[Optional["SubTopic"]] = relationship(back_populates="entities")
    section: Mapped[Optional["Section"]] = relationship(back_populates="entities")
    chunks: Mapped[list["Chunk"]] = relationship(secondary=chunk_entities, back_populates="entities")
    images: Mapped[list["Image"]] = relationship(secondary=image_entities, back_populates="entities")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    topic_id: Mapped[str] = mapped_column(String, ForeignKey("topics.id"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="process")
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    topic: Mapped["Topic"] = relationship(back_populates="jobs")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TopicCreate(BaseModel):
    name: str
    description: Optional[str] = None


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: Optional[str]
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    topic_id: str
    source_type: SourceType
    source_ref: str
    filename: Optional[str]
    page_count: Optional[int]
    minio_key: Optional[str]
    context: Optional[str]
    created_at: datetime


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    topic_id: str
    filename: str
    description: Optional[str]
    minio_key: Optional[str]
    created_at: datetime


class SubTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    topic_id: str
    name: str
    description: Optional[str]
    keywords: Optional[str]
    created_at: datetime


class SubTopicPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ref_id: str
    topic_id: str
    subtopic_id: Optional[str]
    section_id: Optional[str]
    name: str
    description: Optional[str]
    entity_type: Optional[EntityType]
    created_at: datetime


class EntityPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    entity_type: Optional[EntityType] = None
    subtopic_id: Optional[str] = None


class ChunkSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    content: str
    chunk_index: int
    token_count: int


class EntityDetailOut(EntityOut):
    chunks: list[ChunkSummary] = []
    images: list[ImageOut] = []


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    subtopic_id: str
    topic_id: str
    name: str
    description: Optional[str]
    order_index: int
    created_at: datetime


class SectionPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    order_index: Optional[int] = None


class EntityIndexItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    ref_id: str
    name: str
    entity_type: Optional[EntityType]


class SectionIndexItem(BaseModel):
    id: str
    name: str
    description: Optional[str]
    order_index: int
    entities: list[EntityIndexItem]


class SubTopicIndexItem(BaseModel):
    id: str
    name: str
    description: Optional[str]
    sections: list[SectionIndexItem]


class TopicIndex(BaseModel):
    topic_id: str
    topic_name: str
    subtopics: list[SubTopicIndexItem]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    topic_id: str
    type: str
    status: JobStatus
    error: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class IngestUrlRequest(BaseModel):
    url: str
    context: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)


class EntitySearchHit(BaseModel):
    score: float
    entity: EntityOut
    matched_excerpt: str


class ImageSearchHit(BaseModel):
    score: float
    image: ImageOut


class SearchResponse(BaseModel):
    entities: list[EntitySearchHit]
    images: list[ImageSearchHit]


class SmartIngestResult(BaseModel):
    topic_id: str
    topic_name: str
    was_created: bool
    document_id: str
    filename: str


# ── Dossier models ────────────────────────────────────────────────────────────

class Dossier(Base):
    __tablename__ = "dossiers"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    blocks: Mapped[list["DossierBlock"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan", order_by="DossierBlock.order_index"
    )


class DossierBlock(Base):
    __tablename__ = "dossier_blocks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_new_id)
    dossier_id: Mapped[str] = mapped_column(String, ForeignKey("dossiers.id"), nullable=False)
    block_type: Mapped[str] = mapped_column(String, nullable=False)
    ref_id: Mapped[str] = mapped_column(String, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    dossier: Mapped["Dossier"] = relationship(back_populates="blocks")


class DossierBlockResolved(BaseModel):
    id: str
    block_type: str
    ref_id: str
    order_index: int
    label: str
    meta: dict


class DossierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class DossierDetail(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    blocks: list[DossierBlockResolved]


class DossierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class DossierPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)


class DossierBlockCreate(BaseModel):
    block_type: str
    ref_id: str
    order_index: int = Field(0, ge=0)


class DossierBlockPatch(BaseModel):
    order_index: int = Field(..., ge=0)
