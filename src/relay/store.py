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
            self._public(db,rid,'status',{'status':'queued'})
            return rid, True

    def get(self, rid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM requests WHERE id=?', (rid,)).fetchone()
        if not row:
            return None
        return {'id': row['id'], 'status': row['status'], 'created_at': row['created'],
                'updated_at':row['updated'], 'body':json.loads(row['body']),
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
            self._public(db,rid,'status',{'status':status})
            if status in TERMINAL:
                if status=='answered' and result:
                    answer=result.get('answer','')
                    for offset in range(0,len(answer),512):
                        self._public(db,rid,'answer_delta',{'offset':offset,'text':answer[offset:offset+512]})
                    self._public(db,rid,'citations',{'chunk_ids':[c['id'] for c in result.get('citations',[])]})
                elif status=='needs_clarification':
                    self._public(db,rid,'clarification',{'message':(result or {}).get('message')})
                elif status not in ('refused','cancelled'):
                    self._public(db,rid,'error',{'code':(result or {}).get('reason',status)})
                self._public(db,rid,'done',{'status':status,'resource_url':f'/v1/requests/{rid}'})
            return True

    @staticmethod
    def _public(db,rid,event,payload):
        raw=json.dumps({'request_id':rid,**payload},ensure_ascii=False)
        if len(raw.encode())>8192: raise ValueError('public_event_too_large')
        db.execute('INSERT INTO public_events(request_id,created,event,payload) VALUES(?,?,?,?)',
                   (rid,time.time(),event,raw))

    def public_events(self,rid,after=0,limit=100):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM public_events WHERE request_id=? AND seq>? ORDER BY seq LIMIT ?', (rid,after,limit))]

    def cursor_secret(self):
        with self.connect() as db:
            return db.execute("SELECT value FROM local_metadata WHERE key='cursor_secret'").fetchone()[0].encode()

    def history(self, limit=20, before=None, status=None, snapshot=None):
        with self.connect() as db:
            clauses=['created<=?']; values=[snapshot or time.time()]
            if before: clauses.append('(created,id)<(?,?)'); values.extend(before)
            if status: clauses.append('status=?'); values.append(status)
            rows=db.execute('SELECT id FROM requests WHERE '+' AND '.join(clauses)+' ORDER BY created DESC,id DESC LIMIT ?',(*values,limit)).fetchall()
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

    def usage_summary(self,rid):
        with self.connect() as db:
            rows=db.execute("SELECT * FROM calls WHERE request_id=? AND state!='released'",(rid,)).fetchall()
        known=[r for r in rows if r['tokens_in'] is not None and r['tokens_out'] is not None]
        missing=len(rows)-len(known)
        return {'prompt_tokens':sum(r['tokens_in'] for r in known) if not missing else None,
                'completion_tokens':sum(r['tokens_out'] for r in known) if not missing else None,
                'known_prompt_tokens':sum(r['tokens_in'] for r in known),
                'known_completion_tokens':sum(r['tokens_out'] for r in known),
                'unknown_usage_calls':missing,'attempts':len(rows)}

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
