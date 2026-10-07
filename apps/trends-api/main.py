import asyncio
import time
import ssl
from datetime import datetime, timezone
from typing import Literal

import httpx
import truststore
from defusedxml import ElementTree
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Karen Angelis · Trends Lab", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4173", "http://127.0.0.1:4173", "https://karenangelis.com", "https://www.karenangelis.com"],
    allow_methods=["GET"],
)
_cache = {}
_lock = asyncio.Lock()
HT = "{https://trends.google.com/trending/rss}"


def parse_feed(content: bytes) -> list[dict]:
    root = ElementTree.fromstring(content)
    return [
        {"title": item.findtext("title", ""), "traffic": item.findtext(f"{HT}approx_traffic", ""), "published": item.findtext("pubDate", "")}
        for item in root.findall("./channel/item")
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/trends")
async def trends(geo: Literal["BR", "US", "PT"] = "BR", limit: int = Query(10, ge=1, le=20)):
    async with _lock:
        existing = _cache.get(geo)
        cached = existing is not None and time.monotonic() - existing[0] < 300
        if cached:
            data = existing[1]
        else:
            try:
                async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)) as client:
                    response = await client.get("https://trends.google.com/trending/rss", params={"geo": geo})
                    response.raise_for_status()
                items = parse_feed(response.content)
            except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
                raise HTTPException(502, "O feed Google Trends está indisponível. Tente novamente mais tarde.") from exc
            data = {"geo": geo, "source": f"https://trends.google.com/trending/rss?geo={geo}", "fetched_at": datetime.now(timezone.utc).isoformat(), "items": items}
            _cache[geo] = (time.monotonic(), data)
    return {**data, "cached": cached, "items": data["items"][:limit]}
