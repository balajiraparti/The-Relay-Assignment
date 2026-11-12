import concurrent.futures
import sqlite3
import pytest
from relay.migrations import migrate,BASELINE,VERSION
from relay.store import Store


def test_fresh_repeat_and_legacy_upgrade(tmp_path):
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript(BASELINE)
        db.execute("INSERT INTO calls VALUES('call','old-probe','groq',1,10,NULL,NULL,'unknown')")
    assert migrate(path)==VERSION and migrate(path)==VERSION
    assert len(list(tmp_path.glob('*.bak')))==1
    with Store(path).connect() as db:
        assert db.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT kind FROM operations').fetchone()[0]=='legacy'
        assert db.execute('SELECT estimated FROM calls').fetchone()[0]==10


def test_constraints_and_transaction_rollback(tmp_path):
    store=Store(tmp_path/'db'); rid,_=store.create('key','hash',{'question':'test'})
    with pytest.raises(sqlite3.IntegrityError): store.reserve('missing','groq',1,(10,100,10,100))
    with pytest.raises(sqlite3.IntegrityError): store.reserve(rid,'invalid',1,(10,100,10,100))
    with pytest.raises(sqlite3.IntegrityError): store.update(rid,'invalid')
    cid=store.reserve(rid,'groq',1,(10,100,10,100))
    with pytest.raises(sqlite3.IntegrityError): store.call_state(cid,'succeeded',{'prompt_tokens':-1,'completion_tokens':1})
    with pytest.raises(RuntimeError):
        with store.connect() as db:
            db.execute("INSERT INTO operations VALUES('rollback','probe',1)")
            raise RuntimeError('rollback')
    with store.connect() as db:
        assert db.execute("SELECT 1 FROM operations WHERE id='rollback'").fetchone() is None
    store.update(rid,'cancelled')
    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as db: db.execute("UPDATE requests SET status='queued' WHERE id=?",(rid,))


def test_parallel_reservations_cannot_overspend(tmp_path):
    store=Store(tmp_path/'db'); store.operation('probe')
    def reserve(_):
        try: store.reserve('probe','groq',10,(10,30,10,30)); return True
        except ValueError: return False
    with concurrent.futures.ThreadPoolExecutor(6) as pool:
        assert sum(pool.map(reserve,range(12)))==3


def test_failed_migration_preserves_old_database(tmp_path):
    path=tmp_path/'invalid.db'
    with sqlite3.connect(path) as db:
        db.executescript(BASELINE)
        db.execute("INSERT INTO requests VALUES('r','k','h',1,1,'invalid','{}',NULL)")
    with pytest.raises(sqlite3.IntegrityError): migrate(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]==1
        assert db.execute('SELECT status FROM requests').fetchone()[0]=='invalid'
    assert len(list(tmp_path.glob('*.bak')))==1


def test_startup_rejects_schema_mismatch(tmp_path):
    path=tmp_path/'db'
    with pytest.raises(RuntimeError,match='schema_mismatch'): Store(path,initialize=False)
