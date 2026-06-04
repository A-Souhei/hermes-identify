import base64

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import settings

COLLECTION = "entifier_chunks"
VECTOR_SIZE = 1536  # text-embedding-3-small

_openai: AsyncOpenAI | None = None
_qdrant: AsyncQdrantClient | None = None


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(
            api_key=settings.openai_api_key or "sk-placeholder",
            base_url=settings.openai_base_url,
        )
    return _openai


def _get_qdrant() -> AsyncQdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    return _qdrant


async def init_qdrant() -> None:
    client = _get_qdrant()
    collections = await client.get_collections()
    names = {c.name for c in collections.collections}
    if COLLECTION not in names:
        await client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = await _get_openai().embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def upsert_to_qdrant(points: list[dict]) -> None:
    """Each point: {id: str, vector: list[float], payload: dict}."""
    if not points:
        return
    structs = [PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in points]
    await _get_qdrant().upsert(collection_name=COLLECTION, points=structs)


async def search_vectors(query_vector: list[float], topic_id: str, limit: int) -> list:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return await _get_qdrant().search(
        collection_name=COLLECTION,
        query_vector=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="topic_id", match=MatchValue(value=topic_id))]
        ),
        limit=limit,
        with_payload=True,
    )


async def describe_image(image_bytes: bytes, content_type: str) -> str:
    """Use vision LLM to generate a textual description of an image."""
    b64 = base64.b64encode(image_bytes).decode()
    response = await _get_openai().chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe this image in detail. Cover the main subject, "
                            "any visible text, and overall context. "
                            "This description is used for document classification and search."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{content_type};base64,{b64}"},
                    },
                ],
            }
        ],
        max_tokens=500,
    )
    return response.choices[0].message.content or ""
