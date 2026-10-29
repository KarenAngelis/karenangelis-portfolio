import hashlib
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, password TEXT,
                    verified INTEGER NOT NULL DEFAULT 0, google_sub TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS tokens (
                    token TEXT PRIMARY KEY, user_id TEXT, kind TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS quotes (
                    id TEXT PRIMARY KEY, domain TEXT NOT NULL, amount INTEGER NOT NULL,
                    renewal INTEGER NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), domain TEXT NOT NULL,
                    amount INTEGER NOT NULL, renewal INTEGER NOT NULL, registrant TEXT NOT NULL,
                    status TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL,
                    checkout_url TEXT, preference_id TEXT, payment_id TEXT UNIQUE,
                    customer_id TEXT, contact_id TEXT, admin_contact_id TEXT, registrar_order_id TEXT,
                    expires INTEGER, note TEXT, nameservers TEXT NOT NULL DEFAULT '[]',
                    idempotency TEXT NOT NULL, UNIQUE(user_id,idempotency));
                CREATE UNIQUE INDEX IF NOT EXISTS domain_in_flight ON orders(domain)
                    WHERE status NOT IN ('checkout_failed','expired','refunded','cancelled');
                CREATE TABLE IF NOT EXISTS payment_events (
                    payment_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id),
                    status TEXT NOT NULL, updated INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY, order_id TEXT NOT NULL, kind TEXT NOT NULL,
                    created INTEGER NOT NULL, UNIQUE(order_id,kind));
            ''')
        os.chmod(path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def one(self, sql, args=()):
        with self.connection() as db:
            row = db.execute(sql, args).fetchone()
            return dict(row) if row else None

    def all(self, sql, args=()):
        with self.connection() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def execute(self, sql, args=()):
        with self.connection() as db:
            return db.execute(sql, args).rowcount

    def update_order(self, order_id, from_status=None, **values):
        allowed = {'status','checkout_url','preference_id','payment_id','customer_id','contact_id',
                   'admin_contact_id','registrar_order_id','expires','note','nameservers'}
        assert values and set(values) <= allowed
        values['updated'] = int(time.time())
        clause = ' AND status=?' if from_status else ''
        args = (*values.values(), order_id, from_status) if from_status else (*values.values(), order_id)
        return self.execute('UPDATE orders SET ' + ','.join(f'{key}=?' for key in values) + ' WHERE id=?' + clause, args)

    def alert(self, order_id, kind):
        self.execute('INSERT OR IGNORE INTO alerts(order_id,kind,created) VALUES(?,?,?)',
                     (order_id, kind, int(time.time())))

    def allow(self, key, maximum, seconds=60):
        now = int(time.time())
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM limits WHERE expires<?', (now,))
            db.execute('INSERT INTO limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',
                       (hashlib.sha256(key.encode()).hexdigest(), now + seconds))
            row = db.execute('SELECT count FROM limits WHERE key=?',
                             (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
            return row['count'] <= maximum
