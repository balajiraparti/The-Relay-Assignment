import concurrent.futures
import json
import threading
import pytest
from relay.telemetry import Telemetry,TelemetryError,trace
from relay.store import Store


def records(path):
    return [json.loads(line) for file in path.glob('*.jsonl') for line in file.read_text().splitlines()]


def test_correlated_spans_redaction_and_shutdown_flush(tmp_path):
    with Telemetry(tmp_path,secrets=['synthetic-secret'],segment_bytes=1200) as log:
        def work(i):
            with trace(request_id=f'request-{i}'):
                with log.span('fixture'):
                    log.emit('work',nested={'Authorization':'Bearer secret','api-key':'hidden'},
                             question='private query',detail='synthetic-secret',index=i)
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            list(pool.map(work,range(12)))
    rows=records(tmp_path)
    assert len(rows)==38
    assert len({r['event_id'] for r in rows})==38
    assert sorted(r['sequence'] for r in rows)==list(range(1,39))
    for i in range(12):
        group=[r for r in rows if r.get('request_id')==f'request-{i}']
        assert len(group)==3 and len({r['span_id'] for r in group})==1
        assert next(r for r in group if r['event_name']=='fixture_finished')['attributes']['duration_ms']>=0
    serialized=json.dumps(rows)
    assert not any(value in serialized for value in ('synthetic-secret','private query','Bearer secret','hidden'))
    assert len(list(tmp_path.glob('*.jsonl')))>1


def test_store_payload_redacted_before_persistence(tmp_path):
    with Telemetry(tmp_path/'logs',secrets=['synthetic-secret']):
        store=Store(tmp_path/'db'); rid,_=store.create('idem','hash',{'question':'private'})
        store.event(rid,'fixture',answer='private',nested={'value':'synthetic-secret'})
        with store.connect() as db: data=db.execute('SELECT payload FROM events').fetchone()[0]
        assert 'private' not in data and 'synthetic-secret' not in data


def test_writer_failure_is_visible(tmp_path,capsys):
    log=Telemetry(tmp_path,max_bytes=1)
    log.emit('too_large'); log.queue.join()
    assert log.failed and list(tmp_path.glob('*.incomplete'))
    with pytest.raises(TelemetryError): log.emit('later')
    with pytest.raises(TelemetryError): log.close()
    assert 'incomplete' in capsys.readouterr().err


def test_required_overflow_stops_admission(tmp_path):
    gate=threading.Event()
    class Paused(Telemetry):
        def _write(self):
            gate.wait(5); super()._write()
    log=Paused(tmp_path,capacity=1)
    try:
        log.emit('first')
        log.emit('debug',level='DEBUG')
        assert log.dropped_debug==1 and not log.failed
        with pytest.raises(TelemetryError): log.emit('required')
        assert log.failed
    finally:
        gate.set()
        with pytest.raises(TelemetryError): log.close()


def test_async_contexts_do_not_leak(tmp_path):
    import asyncio
    with Telemetry(tmp_path) as log:
        async def work(i):
            with trace(request_id=str(i)):
                await asyncio.sleep(0)
                log.emit('async_fixture',index=i)
        async def run(): await asyncio.gather(*(work(i) for i in range(20)))
        asyncio.run(run())
    rows=[r for r in records(tmp_path) if r['event_name']=='async_fixture']
    assert len(rows)==20
    assert all(r['request_id']==str(r['attributes']['index']) for r in rows)
