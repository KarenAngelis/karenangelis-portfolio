"""Durable records for the private career manager.

Every write uses an immediate SQLite transaction. Database constraints remain the
source of truth when different workers or Store instances access the same file.
Secrets passed to this module must already be encrypted by the integration layer.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class Store:
    def __init__(self, path):
        self.path = str(Path(path).expanduser()) if str(path) != ":memory:" else ":memory:"
        if self.path != ":memory:":
            Path(self.path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, timeout=15, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA busy_timeout=15000")
        self._db.execute("PRAGMA journal_mode=WAL")
        # Each execution context owns its own token. An expired older worker must
        # never release a newer worker's lease, even when sharing one Store.
        self._held_leases = ContextVar("career_leases_" + uuid.uuid4().hex, default=None)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS profile (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                payload TEXT NOT NULL, revision INTEGER NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS answers (
                id TEXT PRIMARY KEY, intent TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
                payload TEXT NOT NULL, match TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(source, external_id)
            );
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id),
                payload TEXT NOT NULL, snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT NOT NULL UNIQUE,
                application_id TEXT REFERENCES applications(id), kind TEXT NOT NULL,
                detail TEXT NOT NULL, source_key TEXT UNIQUE, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_application ON events(application_id, sequence);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS leases (
                name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL
            );
        """)

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def close(self):
        with self._lock:
            self._db.close()

    def _profile(self):
        row = self._db.execute("SELECT * FROM profile WHERE singleton=1").fetchone()
        return {**json.loads(row["payload"]), "revision": row["revision"], "updated_at": row["updated_at"]} if row else {}

    def get_profile(self):
        with self._lock:
            return self._profile()

    def save_profile(self, data):
        payload = deepcopy(dict(data))
        payload.pop("revision", None)
        payload.pop("updated_at", None)
        encoded, now = _json(payload), _now()
        with self._transaction() as db:
            db.execute("""INSERT INTO profile VALUES(1,?,1,?)
                ON CONFLICT(singleton) DO UPDATE SET payload=excluded.payload,
                revision=profile.revision+1, updated_at=excluded.updated_at""", (encoded, now))
            return self._profile()

    @staticmethod
    def _answer(row):
        return {**json.loads(row["payload"]), "id": row["id"], "intent": row["intent"],
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def list_answers(self):
        with self._lock:
            return [self._answer(row) for row in self._db.execute("SELECT * FROM answers ORDER BY intent")]

    def save_answer(self, data):
        payload = deepcopy(dict(data))
        intent = payload.get("intent")
        intent = intent.strip().casefold() if isinstance(intent, str) else ""
        if not intent or not isinstance(payload.get("text"), str) or not payload["text"].strip():
            raise ValueError("A resposta precisa de intenção e texto.")
        payload["intent"] = intent
        for key in ("id", "created_at", "updated_at"):
            payload.pop(key, None)
        with self._transaction() as db:
            now = _now()
            db.execute("""INSERT INTO answers VALUES(?,?,?,?,?)
                ON CONFLICT(intent) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
                (uuid.uuid4().hex, intent, _json(payload), now, now))
            return self._answer(db.execute("SELECT * FROM answers WHERE intent=?", (intent,)).fetchone())

    def delete_answer(self, answer_id):
        with self._transaction() as db:
            result = db.execute("DELETE FROM answers WHERE id=?", (answer_id,))
            return {"deleted": result.rowcount == 1, "id": answer_id}

    @staticmethod
    def _job(row):
        return {**json.loads(row["payload"]), "id": row["id"], "source": row["source"],
                "external_id": row["external_id"], "match": json.loads(row["match"]) if row["match"] else None,
                "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def upsert_job(self, data):
        payload = deepcopy(dict(data))
        source = payload.get("source")
        source = source.strip().casefold() if isinstance(source, str) else ""
        external_id = payload.get("external_id")
        external_id = str(external_id).strip() if external_id is not None else ""
        if not source or not external_id:
            raise ValueError("A vaga precisa de fonte e identificador externo.")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE source=? AND external_id=?", (source, external_id)).fetchone()
            existing = json.loads(row["payload"]) if row else {}
            for key in ("id", "created_at", "updated_at", "match"):
                payload.pop(key, None)
            merged = {**existing, **payload, "source": source, "external_id": external_id}
            now = _now()
            if row:
                # A changed vacancy must be evaluated again before another action.
                encoded = _json(merged)
                db.execute("UPDATE jobs SET payload=?, match=CASE WHEN payload=? THEN match ELSE NULL END, updated_at=? WHERE id=?",
                           (encoded, encoded, now, row["id"]))
                job_id = row["id"]
            else:
                job_id = uuid.uuid4().hex
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,NULL,?,?)", (job_id, source, external_id, _json(merged), now, now))
            return self._job(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def list_jobs(self):
        with self._lock:
            return [self._job(row) for row in self._db.execute("SELECT * FROM jobs ORDER BY created_at DESC, id")]

    def get_job(self, job_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return self._job(row) if row else {}

    def save_match(self, job_id, match):
        with self._transaction() as db:
            result = db.execute("UPDATE jobs SET match=?, updated_at=? WHERE id=?", (_json(match), _now(), job_id))
            if result.rowcount != 1:
                raise KeyError("Vaga não encontrada.")
            return self._job(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    @staticmethod
    def _application(row):
        return {**json.loads(row["payload"]), "id": row["id"], "job_id": row["job_id"],
                "snapshot": json.loads(row["snapshot"]), "created_at": row["created_at"], "updated_at": row["updated_at"]}

    def create_application(self, job_id, data):
        with self._transaction() as db:
            existing = db.execute("SELECT * FROM applications WHERE job_id=?", (job_id,)).fetchone()
            if existing:
                return self._application(existing)
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise KeyError("Vaga não encontrada.")
            payload = deepcopy(dict(data))
            for key in ("id", "job_id", "snapshot", "created_at", "updated_at"):
                payload.pop(key, None)
            payload.setdefault("status", "prepared")
            snapshot = {"profile": self._profile(), "job": self._job(job),
                        "answers": [self._answer(row) for row in db.execute("SELECT * FROM answers ORDER BY intent")],
                        "initial_data": deepcopy(payload)}
            app_id, now = uuid.uuid4().hex, _now()
            db.execute("INSERT INTO applications VALUES(?,?,?,?,?,?)", (app_id, job_id, _json(payload), _json(snapshot), now, now))
            self._add_event(db, app_id, "application.created", {"status": payload["status"]}, "application.created:" + app_id)
            return self._application(db.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone())

    def list_applications(self):
        with self._lock:
            return [self._application(row) for row in self._db.execute("SELECT * FROM applications ORDER BY created_at DESC, id")]

    def get_application(self, application_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
            return self._application(row) if row else {}

    def update_application(self, application_id, data):
        with self._transaction() as db:
            row = db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone()
            if row is None:
                raise KeyError("Candidatura não encontrada.")
            changes = deepcopy(dict(data))
            for key in ("id", "job_id", "snapshot", "created_at", "updated_at"):
                changes.pop(key, None)
            payload = json.loads(row["payload"])
            changed = {key: value for key, value in changes.items() if key not in payload or payload[key] != value}
            if changed:
                payload.update(changed)
                db.execute("UPDATE applications SET payload=?, updated_at=? WHERE id=?", (_json(payload), _now(), application_id))
                self._add_event(db, application_id, "application.updated", {"changes": changed}, None)
            return self._application(db.execute("SELECT * FROM applications WHERE id=?", (application_id,)).fetchone())

    @staticmethod
    def _event(row):
        return {"id": row["id"], "sequence": row["sequence"], "application_id": row["application_id"],
                "kind": row["kind"], "detail": json.loads(row["detail"]),
                "source_key": row["source_key"], "created_at": row["created_at"]}

    def _add_event(self, db, application_id, kind, detail, source_key):
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("O evento precisa de um tipo.")
        if source_key is not None:
            existing = db.execute("SELECT * FROM events WHERE source_key=?", (source_key,)).fetchone()
            if existing:
                if existing["application_id"] != application_id or existing["kind"] != kind:
                    raise ValueError("A origem do evento já foi usada para outra ação.")
                return self._event(existing)
        event_id = uuid.uuid4().hex
        db.execute("INSERT INTO events(id,application_id,kind,detail,source_key,created_at) VALUES(?,?,?,?,?,?)",
                   (event_id, application_id, kind, _json(detail), source_key, _now()))
        return self._event(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone())

    def add_event(self, application_id, kind, detail, source_key=None):
        with self._transaction() as db:
            return self._add_event(db, application_id, kind, detail, source_key)

    def list_events(self, application_id=None):
        with self._lock:
            query = "SELECT * FROM events"
            args = ()
            if application_id is not None:
                query += " WHERE application_id=?"
                args = (application_id,)
            return [self._event(row) for row in self._db.execute(query + " ORDER BY sequence", args)]

    def get_setting(self, key, default=None):
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return json.loads(row["value"]) if row else deepcopy(default)

    def set_setting(self, key, value):
        with self._transaction() as db:
            db.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, _json(value)))
            return {"key": key, "value": deepcopy(value)}

    def get_secret(self, key):
        with self._lock:
            row = self._db.execute("SELECT value FROM secrets WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None

    def set_secret(self, key, value):
        if not isinstance(value, str):
            raise ValueError("Segredo cifrado deve ser uma string.")
        with self._transaction() as db:
            db.execute("INSERT INTO secrets VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            return {"key": key, "stored": True}

    def try_lock(self, name, ttl=300):
        if not isinstance(ttl, (int, float)) or ttl <= 0:
            raise ValueError("A duração do bloqueio deve ser positiva.")
        with self._transaction() as db:
            now = time.time()
            owner = uuid.uuid4().hex
            result = db.execute("""INSERT INTO leases VALUES(?,?,?) ON CONFLICT(name) DO UPDATE
                SET owner=excluded.owner, expires_at=excluded.expires_at WHERE leases.expires_at<=?""",
                (name, owner, now + ttl, now))
            if result.rowcount == 1:
                self._held_leases.set({**(self._held_leases.get() or {}), name: owner})
            return {"name": name, "acquired": result.rowcount == 1, "expires_at": now + ttl if result.rowcount == 1 else None}

    def release_lock(self, name):
        with self._transaction() as db:
            held = dict(self._held_leases.get() or {})
            owner = held.pop(name, None)
            result = db.execute("DELETE FROM leases WHERE name=? AND owner=?", (name, owner))
            self._held_leases.set(held)
            return {"name": name, "released": result.rowcount == 1}
