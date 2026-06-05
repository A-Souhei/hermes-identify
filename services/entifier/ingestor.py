import io
import json as _json

import httpx
from pypdf import PdfReader

from config import settings


async def parse_pdf(content: bytes) -> tuple[str, int]:
    """Return (extracted_text, page_count)."""
    reader = PdfReader(io.BytesIO(content))
    text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return text.strip(), len(reader.pages)


def parse_md(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").strip()


def parse_csv(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").strip()


def parse_json(content: bytes) -> str:
    try:
        data = _json.loads(content.decode("utf-8", errors="replace"))
        return _json.dumps(data, indent=2, ensure_ascii=False)
    except _json.JSONDecodeError:
        return content.decode("utf-8", errors="replace").strip()


def parse_yaml(content: bytes) -> str:
    return content.decode("utf-8", errors="replace").strip()


async def fetch_url(url: str) -> str:
    """Fetch and return markdown content via self-hosted Firecrawl."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{settings.firecrawl_url}/v1/scrape",
            json={"url": url, "formats": ["markdown"]},
        )
        r.raise_for_status()
        data = r.json()
        return data["data"]["markdown"]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks (approximate token count via char proxy)."""
    char_size = chunk_size * 4
    char_overlap = overlap * 4

    text = text.strip()
    if not text:
        return []
    if len(text) <= char_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + char_size, len(text))
        chunk = text[start:end]
        if end < len(text):
            for sep in ["\n\n", "\n", ". ", " "]:
                idx = chunk.rfind(sep)
                if idx > char_size // 2:
                    chunk = chunk[: idx + len(sep)]
                    break
        stripped = chunk.strip()
        if stripped:
            chunks.append(stripped)
        advance = max(len(chunk) - char_overlap, 1)
        start += advance

    return chunks
