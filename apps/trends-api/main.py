import asyncio
import time
import ssl
import unicodedata
from datetime import datetime, timezone
from typing import Literal

import httpx
import truststore
from defusedxml import ElementTree
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Karen Angelis · Notícias", version="0.3.0")
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
        {"title": item.findtext("title", ""), "traffic": item.findtext(f"{HT}approx_traffic", ""), "published": item.findtext("pubDate", ""), "url": item.findtext("link", ""), "publisher": item.findtext("source", "")}
        for item in root.findall("./channel/item")
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/news")
async def news(q: str = Query(..., min_length=1, max_length=100), geo: Literal["BR", "US", "PT", "IT"] = "BR", limit: int = Query(10, ge=1, le=20)):
    if not q.strip():
        raise HTTPException(422, "Digite um assunto para buscar notícias.")
    result = await trends(geo=geo, limit=limit, q=q)
    return {**result, "items": [{key: item[key] for key in ("title", "published", "url", "publisher")} for item in result["items"]]}


@app.get("/api/trends", include_in_schema=False)
async def trends(geo: Literal["BR", "US", "PT", "IT"] = "BR", limit: int = Query(10, ge=1, le=20), q: str = Query("", max_length=100)):
    query = " ".join(q.split())
    if any(unicodedata.category(char).startswith("C") for char in query):
        raise HTTPException(422, "Use um assunto em texto, sem caracteres de controle.")
    key = (geo, query.casefold())
    mode = "news" if query else "trending"
    language = {"BR": "pt-BR", "PT": "pt-PT", "US": "en-US", "IT": "it-IT"}[geo]
    source = "https://news.google.com/rss/search" if query else "https://trends.google.com/trending/rss"
    params = {"q": query, "hl": language, "gl": geo, "ceid": f"{geo}:{language.split('-')[0]}"} if query else {"geo": geo}
    async with _lock:
        existing = _cache.get(key)
        cached = existing is not None and time.monotonic() - existing[0] < 300
        if cached:
            data = existing[1]
        else:
            try:
                async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)) as client:
                    response = await client.get(source, params=params)
                    response.raise_for_status()
                items = parse_feed(response.content)
            except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
                raise HTTPException(502, "A fonte de dados está indisponível. Tente novamente mais tarde.") from exc
            data = {"geo": geo, "mode": mode, "source": str(response.url), "fetched_at": datetime.now(timezone.utc).isoformat(), "items": items}
            if len(_cache) >= 128:
                _cache.pop(next(iter(_cache)))
            _cache[key] = (time.monotonic(), data)
    return {**data, "query": query, "cached": cached, "items": data["items"][:limit]}
