"""Transactional numbered migrations for the v0.1 persistence foundation."""
import sqlite3
import time
from pathlib import Path

VERSION=2
BASELINE='''
CREATE TABLE schema_version(version INTEGER PRIMARY KEY);
INSERT INTO schema_version VALUES(1);
CREATE TABLE requests(id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, body_hash TEXT NOT NULL,
created REAL NOT NULL, updated REAL NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, result TEXT);
CREATE INDEX request_history ON requests(created DESC,id DESC);
CREATE TABLE calls(id TEXT PRIMARY KEY, request_id TEXT NOT NULL, source TEXT NOT NULL,
created REAL NOT NULL, estimated INTEGER NOT NULL CHECK(estimated>=0), tokens_in INTEGER, tokens_out INTEGER, state TEXT NOT NULL);
CREATE INDEX call_window ON calls(source,created);
CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT,
created REAL NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL);
'''
FOUNDATION='''
CREATE TABLE operations(id TEXT PRIMARY KEY NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('request','probe','legacy')), created REAL NOT NULL);
INSERT INTO operations SELECT id,'request',created FROM requests;
INSERT OR IGNORE INTO operations SELECT request_id,'legacy',created FROM calls;
INSERT OR IGNORE INTO operations SELECT request_id,'legacy',created FROM events WHERE request_id IS NOT NULL;
CREATE TABLE requests_new(
id TEXT PRIMARY KEY NOT NULL REFERENCES operations(id), idem TEXT UNIQUE NOT NULL CHECK(length(idem)>0), body_hash TEXT NOT NULL,
created REAL NOT NULL, updated REAL NOT NULL CHECK(updated>=created),
status TEXT NOT NULL CHECK(status IN ('queued','preparing','retrieving','reranking','generating','validating','answered','refused','needs_clarification','failed','timed_out','cancelled','rate_limited')),
body TEXT NOT NULL CHECK(json_valid(body)), result TEXT CHECK(result IS NULL OR json_valid(result)));
INSERT INTO requests_new SELECT * FROM requests;
DROP TABLE requests;
ALTER TABLE requests_new RENAME TO requests;
CREATE INDEX request_history ON requests(created DESC,id DESC);
CREATE TABLE calls_new(
id TEXT PRIMARY KEY NOT NULL, request_id TEXT NOT NULL REFERENCES operations(id),
source TEXT NOT NULL CHECK(source IN ('groq','stand-in')), created REAL NOT NULL,
estimated INTEGER NOT NULL CHECK(estimated>=0), tokens_in INTEGER CHECK(tokens_in>=0), tokens_out INTEGER CHECK(tokens_out>=0),
state TEXT NOT NULL CHECK(state IN ('reserved','dispatched','succeeded','failed','unknown','released')));
INSERT INTO calls_new SELECT * FROM calls;
DROP TABLE calls;
ALTER TABLE calls_new RENAME TO calls;
CREATE INDEX call_window ON calls(source,created);
CREATE TABLE events_new(seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT REFERENCES operations(id),
created REAL NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)));
INSERT INTO events_new SELECT * FROM events;
DROP TABLE events;
ALTER TABLE events_new RENAME TO events;
CREATE INDEX event_request ON events(request_id,seq);
CREATE TRIGGER terminal_immutable BEFORE UPDATE ON requests
WHEN OLD.status IN ('answered','refused','needs_clarification','failed','timed_out','cancelled','rate_limited')
BEGIN SELECT RAISE(ABORT,'terminal_request_immutable'); END;
INSERT INTO schema_version VALUES(2);
'''


def check(db):
    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
        raise RuntimeError('database_integrity_failed')


def version(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='schema_version'").fetchone(): return 0
    return db.execute('SELECT COALESCE(MAX(version),0) FROM schema_version').fetchone()[0]


def migrate(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=5)
    try:
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA journal_mode=WAL')
        old=version(db)
        if old>VERSION: raise RuntimeError('database_schema_newer_than_application')
        if old==VERSION: check(db); return old
        if old:
            backup=sqlite3.connect(str(path)+f'.pre-v{VERSION}.{time.time_ns()}.bak')
            try: db.backup(backup); check(backup)
            finally: backup.close()
        # execute statements individually so DDL/copy/version update share one transaction.
        db.execute('BEGIN IMMEDIATE')
        sql=(BASELINE if old==0 else '')+FOUNDATION
        statement=''
        for line in sql.splitlines(keepends=True):
            statement+=line
            if sqlite3.complete_statement(statement):
                db.execute(statement); statement=''
        check(db); db.commit(); return VERSION
    except BaseException:
        db.rollback(); raise
    finally: db.close()
