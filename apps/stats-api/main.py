"""Contagem de visitas e cliques do portfólio.

Guarda apenas totais por dia. Não usa cookies e não grava IP, user agent nem eventos individuais.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Karen Angelis · Estatísticas", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4173", "http://127.0.0.1:4173", "https://karenangelis.com", "https://www.karenangelis.com"],
    allow_methods=["GET", "POST"],
    allow_headers=[],
)

PATH = re.compile(r"^/[A-Za-z0-9/_.-]{0,80}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9:._/-]{0,59}$")
HOST = re.compile(r"^[a-z0-9.-]{1,80}$")
LANGUAGES = {"pt-BR", "pt-PT", "en-US", "it-IT"}
DEVICES = {"mobile", "desktop"}
BOTS = re.compile(r"bot|crawl|spider|slurp|headless|preview|monitor|curl|wget|python", re.I)
MAX_KEYS = 200  # chaves distintas por dia e por tipo; o excedente cai em "outros"

_lock = threading.Lock()
_db = None
_salt = (date.today(), secrets.token_bytes(16))
_visitors: set[bytes] = set()
_hits: dict[bytes, list[float]] = {}


def database() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = sqlite3.connect(os.getenv("STATS_DB", "stats.sqlite3"), check_same_thread=False)
        _db.execute("CREATE TABLE IF NOT EXISTS counts (day TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, total INTEGER NOT NULL, PRIMARY KEY (day, kind, key))")
        _db.execute("DROP TABLE IF EXISTS panel_auth")
        _db.commit()
    return _db


def reset(path: str = ":memory:") -> None:
    """Reinicia o estado (usado nos testes)."""
    global _db
    os.environ["STATS_DB"] = path
    if _db is not None:
        _db.close()
    _db = None
    _visitors.clear()
    _hits.clear()


def client_address(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")


def fingerprint(request: Request, include_browser: bool = True) -> bytes:
    """Identificador efêmero: IP para limites, IP+navegador para estimar visitantes."""
    global _salt
    today = date.today()
    if _salt[0] != today:
        _salt = (today, secrets.token_bytes(16))
        _visitors.clear()
    browser = request.headers.get("user-agent", "") if include_browser else ""
    return hashlib.sha256(_salt[1] + client_address(request).encode() + browser.encode()).digest()[:12]


def allowed(bucket: dict[bytes, list[float]], who: bytes, limit: int, window: float = 60.0) -> bool:
    now = time.monotonic()
    recent = [moment for moment in bucket.get(who, []) if now - moment < window]
    if len(recent) >= limit:
        bucket[who] = recent
        return False
    recent.append(now)
    bucket[who] = recent
    if len(bucket) > 5000:
        bucket.pop(next(iter(bucket)))
    return True


def add(db: sqlite3.Connection, day: str, kind: str, key: str) -> None:
    known = db.execute("SELECT 1 FROM counts WHERE day=? AND kind=? AND key=?", (day, kind, key)).fetchone()
    if not known and db.execute("SELECT COUNT(*) FROM counts WHERE day=? AND kind=?", (day, kind)).fetchone()[0] >= MAX_KEYS:
        key = "outros"
    db.execute("INSERT INTO counts VALUES (?,?,?,1) ON CONFLICT(day, kind, key) DO UPDATE SET total=total+1", (day, kind, key))


@app.get("/api/stats/health")
def health():
    return {"status": "ok"}


@app.post("/api/stats/event", status_code=204)
async def event(request: Request):
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return Response(status_code=204)
    body = await request.body()
    if len(body) > 600:
        raise HTTPException(413, "Evento grande demais.")
    try:
        data = json.loads(body)
        kind, path = data["type"], data["path"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, "Evento inválido.") from exc
    name, referrer = data.get("name", ""), data.get("referrer", "")
    if kind not in ("view", "click") or not isinstance(path, str) or not PATH.match(path):
        raise HTTPException(422, "Evento inválido.")
    if kind == "click" and not (isinstance(name, str) and NAME.match(name)):
        raise HTTPException(422, "Nome de clique inválido.")
    if BOTS.search(request.headers.get("user-agent", "")):
        return Response(status_code=204)
    who = fingerprint(request)
    rate_key = fingerprint(request, include_browser=False)
    with _lock:
        if not allowed(_hits, rate_key, 90):
            raise HTTPException(429, "Muitos eventos em pouco tempo.")
        db, day = database(), date.today().isoformat()
        if kind == "click":
            add(db, day, "click", name)
        else:
            add(db, day, "view", path)
            if data.get("lang") in LANGUAGES:
                add(db, day, "lang", data["lang"])
            if data.get("device") in DEVICES:
                add(db, day, "device", data["device"])
            if isinstance(referrer, str) and HOST.match(referrer):
                add(db, day, "referrer", referrer)
            if who not in _visitors:
                _visitors.add(who)
                add(db, day, "visitors", "all")
        db.commit()
    return Response(status_code=204)


@app.get("/api/stats/summary")
def summary(days: int = Query(30, ge=1, le=365)):
    with _lock:
        today = date.today()
        period = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
        rows = database().execute("SELECT day, kind, key, total FROM counts WHERE day>=?", (period[0],)).fetchall()
    series = {day: {"day": day, "views": 0, "visitors": 0, "clicks": 0} for day in period}
    tops: dict[str, dict[str, int]] = {"view": {}, "click": {}, "referrer": {}, "lang": {}, "device": {}}
    for day, kind, key, total in rows:
        if day not in series:
            continue
        if kind == "visitors":
            series[day]["visitors"] += total
            continue
        if kind == "view":
            series[day]["views"] += total
        elif kind == "click":
            series[day]["clicks"] += total
        tops[kind][key] = tops[kind].get(key, 0) + total
    ranked = {kind: [{"key": key, "total": total} for key, total in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:25]] for kind, values in tops.items()}
    daily = list(series.values())
    return {
        "days": days,
        "totals": {field: sum(entry[field] for entry in daily) for field in ("views", "visitors", "clicks")},
        "daily": daily,
        "pages": ranked["view"], "clicks": ranked["click"], "referrers": ranked["referrer"], "languages": ranked["lang"], "devices": ranked["device"],
    }
