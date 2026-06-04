from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import create_tables, get_session
from models import Topic, TopicCreate, TopicOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="hermes-entifier", version="0.1.0", lifespan=lifespan)

DB = Annotated[AsyncSession, Depends(get_session)]


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


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
