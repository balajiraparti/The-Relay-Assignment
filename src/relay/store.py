"""Small versioned SQLite store for the first vertical slice."""
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from relay.migrations import migrate, version, VERSION
from relay.telemetry import redact, current

TERMINAL = {'answered', 'refused', 'needs_clarification', 'failed', 'timed_out', 'cancelled', 'rate_limited'}


class Store:
    def __init__(self, path: Path, *, initialize=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.telemetry = current()
        if initialize: migrate(path)
        with self.connect() as db:
            if version(db)!=VERSION: raise RuntimeError('schema_mismatch_run_migrate')

    def operation(self, rid, kind='probe'):
        with self.connect() as db:
            db.execute('INSERT INTO operations VALUES(?,?,?)',(rid,kind,time.time()))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create(self, idem, body_hash, body):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM requests WHERE idem=?', (idem,)).fetchone()
            if row:
                if row['body_hash'] != body_hash:
                    raise ValueError('idempotency_conflict')
                return row['id'], False
            rid = str(uuid.uuid4())
            now = time.time()
            db.execute('INSERT INTO operations VALUES(?,?,?)',(rid,'request',now))
            db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,NULL)',
                       (rid, idem, body_hash, now, now, 'queued', json.dumps(body)))
            return rid, True

    def get(self, rid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM requests WHERE id=?', (rid,)).fetchone()
        if not row:
            return None
        return {'id': row['id'], 'status': row['status'], 'created_at': row['created'],
                'question': json.loads(row['body'])['question'],
                'result': json.loads(row['result']) if row['result'] else None}

    def update(self, rid, status, result=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM requests WHERE id=?', (rid,)).fetchone()
            if not row or row['status'] in TERMINAL:
                return False
            db.execute('UPDATE requests SET status=?,updated=?,result=? WHERE id=?',
                       (status, time.time(), json.dumps(result) if result else None, rid))
            return True

    def history(self, limit=20, before=None):
        with self.connect() as db:
            if before:
                rows = db.execute('SELECT id FROM requests WHERE (created,id)<(?,?) ORDER BY created DESC,id DESC LIMIT ?',
                                  (before[0], before[1], limit)).fetchall()
            else:
                rows = db.execute('SELECT id FROM requests ORDER BY created DESC,id DESC LIMIT ?', (limit,)).fetchall()
        return [self.get(r['id']) for r in rows]

    def event(self, rid, name, **safe_fields):
        safe_fields=redact(safe_fields,self.telemetry.secrets if self.telemetry else ())
        if self.telemetry: self.telemetry.emit(name,request_id=rid,**safe_fields)
        with self.connect() as db:
            db.execute('INSERT INTO events(request_id,created,event,payload) VALUES(?,?,?,?)',
                       (rid, time.time(), name, json.dumps(safe_fields)))

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE calls SET state='unknown' WHERE state='dispatched'")
            db.execute("UPDATE calls SET state='released' WHERE state='reserved'")
            active = db.execute('SELECT id,status FROM requests').fetchall()
        for row in active:
            if row['status'] not in TERMINAL:
                self.update(row['id'], 'failed', {'reason': 'process_interrupted'})

    def reserve(self, rid, source, amount, limits):
        """Conservative rolling 60s/24h caps; not a claim about provider reset rules."""
        now = time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            cooldown=db.execute('SELECT until FROM provider_cooldowns WHERE source=?',(source,)).fetchone()
            if cooldown and cooldown['until']>now: raise ValueError('provider_cooldown')
            rows = db.execute("SELECT * FROM calls WHERE source=? AND created>? AND state!='released'", (source, now-86400)).fetchall()
            for seconds, req_cap, tok_cap, label in [(60, limits[0], limits[1], 'minute'), (86400, limits[2], limits[3], 'day')]:
                active = [r for r in rows if r['created'] > now-seconds]
                used = sum((r['tokens_in']+r['tokens_out']) if r['tokens_in'] is not None and r['tokens_out'] is not None else r['estimated'] for r in active)
                if len(active)+1 > req_cap or used+amount > tok_cap:
                    raise ValueError('local_quota_' + label)
            cid = str(uuid.uuid4())
            db.execute('INSERT INTO calls VALUES(?,?,?,?,?,NULL,NULL,?)', (cid,rid,source,now,amount,'reserved'))
        return cid

    def cooldown(self,source,delay=None):
        with self.connect() as db:
            if delay is not None:
                db.execute('INSERT INTO provider_cooldowns VALUES(?,?) ON CONFLICT(source) DO UPDATE SET until=MAX(until,excluded.until)',
                           (source,time.time()+delay))
            row=db.execute('SELECT until FROM provider_cooldowns WHERE source=?',(source,)).fetchone()
            return max(0.,row['until']-time.time()) if row else 0.

    def call_state(self, cid, state, usage=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT state FROM calls WHERE id=?',(cid,)).fetchone()
            if not row: raise ValueError('unknown_call')
            if state=='released' and row['state'] not in ('reserved','released'):
                raise ValueError('cannot_release_dispatched_usage')
            if usage:
                db.execute('UPDATE calls SET state=?,tokens_in=?,tokens_out=? WHERE id=?',
                           (state,usage.get('prompt_tokens'),usage.get('completion_tokens'),cid))
            else:
                db.execute('UPDATE calls SET state=? WHERE id=?', (state,cid))
