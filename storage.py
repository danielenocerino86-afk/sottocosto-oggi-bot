"""Durable state. PostgreSQL for ephemeral runners; SQLite for a persistent host.

Claims are committed BEFORE network I/O. Pending/unknown sends never expire:
Telegram has no idempotency key, so an operator must reconcile ambiguous sends.
"""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import datetime as dt
import json
import os
import re
import sqlite3
import time
import uuid
from zoneinfo import ZoneInfo


def cents(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 < amount < 100000:
            raise ValueError('Invalid price')
        return int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid price') from None


class Store:
    def __init__(self, url=None, initialize=True):
        self.url = url or os.environ.get('DATABASE_URL')
        if not self.url:
            if os.environ.get('GITHUB_ACTIONS') == 'true':
                raise RuntimeError('DATABASE_URL required on ephemeral runners')
            self.url = 'sqlite:///deals.sqlite3'
        self.pg = self.url.startswith(('postgres://', 'postgresql://'))
        if not self.pg and not self.url.startswith('sqlite:///'):
            raise ValueError('Unsupported database URL')
        if not initialize:
            return
        with self.tx() as db:
            for sql in (
                'CREATE TABLE IF NOT EXISTS claims (key TEXT PRIMARY KEY, token TEXT NOT NULL, state TEXT NOT NULL, updated DOUBLE PRECISION NOT NULL)',
                'CREATE TABLE IF NOT EXISTS publications (token TEXT PRIMARY KEY, key TEXT NOT NULL, price INTEGER, ts DOUBLE PRECISION NOT NULL, day TEXT NOT NULL, payload TEXT NOT NULL)',
                'CREATE INDEX IF NOT EXISTS publications_key_ts ON publications(key, ts)',
                'CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, asin TEXT NOT NULL, price INTEGER NOT NULL, ts DOUBLE PRECISION NOT NULL, score DOUBLE PRECISION NOT NULL, payload TEXT NOT NULL)',
                'CREATE INDEX IF NOT EXISTS observations_asin_ts ON observations(asin, ts)',
                'CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, started DOUBLE PRECISION NOT NULL, finished DOUBLE PRECISION, status TEXT NOT NULL)',
                'CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
            ):
                db.execute(sql)

    @contextmanager
    def tx(self):
        if self.pg:
            import psycopg
            conn = psycopg.connect(self.url, connect_timeout=10)
        else:
            conn = sqlite3.connect(self.url[len('sqlite:///'):], timeout=30)
            conn.execute('PRAGMA busy_timeout=30000')
            conn.execute('BEGIN IMMEDIATE')
        class DB:
            def execute(_, sql, args=()):
                return conn.execute(sql.replace('?', '%s') if self.pg else sql, args)
        try:
            yield DB()
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def claim(self, key, price=None, now=None):
        now = time.time() if now is None else now
        price = cents(price) if price is not None else None
        token = uuid.uuid4().hex
        with self.tx() as db:
            db.execute("INSERT INTO claims VALUES (?, ?, 'idle', ?) ON CONFLICT(key) DO NOTHING", (key, token, now))
            row = db.execute('SELECT state FROM claims WHERE key=?' + (' FOR UPDATE' if self.pg else ''), (key,)).fetchone()
            if row[0] in ('pending', 'unknown'):
                return None
            prev = db.execute('SELECT price, ts FROM publications WHERE key=? ORDER BY ts DESC LIMIT 1', (key,)).fetchone()
            if prev and (price is None or (prev[1] > now - 14 * 86400 and (prev[0] is None or price * 100 > prev[0] * 95))):
                return None
            db.execute("UPDATE claims SET token=?, state='pending', updated=? WHERE key=?", (token, now, key))
        return token

    def finish(self, key, token, state, deal=None):
        if state not in ('sent', 'rejected', 'unknown'):
            raise ValueError('Invalid state')
        now = time.time()
        day = dt.datetime.fromtimestamp(now, ZoneInfo('Europe/Rome')).date().isoformat()
        with self.tx() as db:
            result = db.execute("UPDATE claims SET state=?, updated=? WHERE key=? AND token=? AND state='pending'", (state, now, key, token))
            if result.rowcount != 1:
                raise RuntimeError('Claim ownership lost')
            if state == 'sent':
                deal = deal or {}
                db.execute('INSERT INTO publications VALUES (?, ?, ?, ?, ?, ?)', (token, key, cents(deal['current_price']) if 'current_price' in deal else None, now, day, json.dumps(deal)))

    def observe(self, deal, score):
        with self.tx() as db:
            db.execute('INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)', (uuid.uuid4().hex, deal['asin'], cents(deal['current_price']), time.time(), score, json.dumps(deal)))

    def minimum(self, asin):
        with self.tx() as db:
            value = db.execute('SELECT MIN(price) FROM observations WHERE asin=? AND ts>?', (asin, time.time() - 30 * 86400)).fetchone()[0]
            return value / 100 if value else None

    def history(self):
        with self.tx() as db:
            rows = db.execute('SELECT key, price, ts, day FROM publications WHERE ts>? ORDER BY ts', (time.time() - 14 * 86400,)).fetchall()
        result = {}
        for key, price, ts, day in rows:
            if key.startswith('_'):
                key = key.split(':')[0]
                value = True
            else:
                value = {'price': price / 100 if price else None, 'ts': dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()}
            result.setdefault(day, {})[key] = value
        return result

    def stats(self):
        with self.tx() as db:
            rows = db.execute('SELECT day, payload FROM publications WHERE ts>? ORDER BY ts', (time.time() - 7 * 86400,)).fetchall()
        result = {}
        for day, payload in rows:
            deal = json.loads(payload)
            if deal.get('asin'):
                result.setdefault(day, []).append(deal)
        return result

    def start_run(self):
        run = uuid.uuid4().hex
        with self.tx() as db:
            db.execute("INSERT INTO runs VALUES (?, ?, NULL, 'running')", (run, time.time()))
        return run

    def end_run(self, run, status):
        with self.tx() as db:
            db.execute('UPDATE runs SET finished=?, status=? WHERE id=?', (time.time(), status, run))
            db.execute('DELETE FROM observations WHERE ts<?', (time.time() - 30 * 86400,))
            db.execute('DELETE FROM runs WHERE started<?', (time.time() - 90 * 86400,))

    def status(self):
        with self.tx() as db:
            runs = db.execute('SELECT started, finished, status FROM runs ORDER BY started DESC LIMIT 20').fetchall()
            unresolved = db.execute("SELECT key, state, updated FROM claims WHERE state IN ('pending', 'unknown') ORDER BY updated DESC LIMIT 100").fetchall()
            rows = db.execute('SELECT ts, payload FROM publications ORDER BY ts DESC LIMIT 100').fetchall()
        # Explicit allowlist: never export arbitrary payload, connection details or secrets.
        deals = []
        for ts, raw in rows:
            d = json.loads(raw)
            if d.get('asin'):
                deals.append({k: d.get(k) for k in ('asin', 'title', 'current_price', 'discount_percent', 'score') } | {'ts': ts})
        latest = runs[0] if runs else None
        healthy = bool(latest and latest[2] == 'ok' and latest[1] and time.time() - latest[1] < 3600 and not unresolved)
        return {'generated_at': time.time(), 'healthy': healthy, 'runs': [{'started': r[0], 'finished': r[1], 'status': r[2]} for r in runs], 'unresolved': [{'key': r[0], 'state': r[1], 'updated': r[2]} for r in unresolved], 'deals': deals}

    def resolve(self, key, sent, deal=None):
        """Operator-only reconciliation after checking Telegram; never called automatically."""
        with self.tx() as db:
            row = db.execute("SELECT token FROM claims WHERE key=? AND state IN ('pending','unknown')" + (' FOR UPDATE' if self.pg else ''), (key,)).fetchone()
            if not row:
                raise ValueError('No unresolved claim')
            db.execute("UPDATE claims SET state='pending' WHERE key=?", (key,))
        self.finish(key, row[0], 'sent' if sent else 'rejected', deal)
