"""Actual loopback HTTP/SSE tests; these do not establish Groq behaviour."""
import asyncio
from contextlib import contextmanager
import socket
import threading
import time
import uuid
import pytest
import uvicorn
from relay.backends import HTTPBackend,ModelError
from relay.config import Settings
from relay.gateway import Gateway
from relay.standin import Profile,create_app
from relay.store import Store


@pytest.fixture
def service(tmp_path):
    @contextmanager
    def start(**overrides):
        profile=Profile(first_delay=0,chunk_delay=0,calibration=None,rpm=100,tpm=100000,rpd=10000,tpd=10000000,
                        log_dir=tmp_path/'logs',**overrides)
        app=create_app(profile)
        sock=socket.socket(); sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='on'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True); thread.start()
        deadline=time.monotonic()+10
        while not server.started and thread.is_alive() and time.monotonic()<deadline: time.sleep(.01)
        try:
            assert server.started,'stand-in failed startup'
            yield app,f'http://127.0.0.1:{port}'
        finally:
            server.should_exit=True; thread.join(10); sock.close()
            assert not thread.is_alive(),'stand-in failed shutdown'
    return start


def setup(tmp_path,url,**overrides):
    cfg=Settings(_env_file=None,groq_api_key='',relay_backend='stand-in',standin_url=url,
                 groq_rpm=100,groq_tpm=100000,groq_rpd=10000,groq_tpd=10000000,**overrides)
    store=Store(tmp_path/(uuid.uuid4().hex+'.db'))
    return cfg,store,Gateway(cfg,store)


def rid(store):
    value=uuid.uuid4().hex; store.operation(value); return value


MESSAGES=[{'role':'user','content':'Evidence ['+'a'*20+'] fixture'}]


def test_retry_header_rejects_nonfinite_values():
    from relay.backends import retry_seconds
    assert retry_seconds('NaN') is None and retry_seconds('inf') is None
    assert retry_seconds('2.5')==2.5 and retry_seconds('not a date') is None


def test_stream_events_and_usage(service,tmp_path):
    with service() as (app,url):
        cfg,store,gateway=setup(tmp_path,url)
        request=rid(store)
        result=asyncio.run(gateway.generate(request,MESSAGES))
        assert result['http_status']==200
        assert result['retries']==0 and result['usage']['completion_tokens']>0
        assert 'Synthetic' in result['text']
        with store.connect() as db: assert db.execute('SELECT state FROM calls').fetchone()[0]=='succeeded'
        assert any(e['event']=='standin_completed' and e['request_id']==request for e in app.state.observed)


def test_transient_503_retries_then_succeeds(service,tmp_path):
    with service(fail_first_requests=1) as (app,url):
        cfg,store,gateway=setup(tmp_path,url,retry_base_delay=.01)
        result=asyncio.run(gateway.generate(rid(store),MESSAGES))
        assert result['retries']==1 and app.state.count==2
        with store.connect() as db:
            assert [r[0] for r in db.execute('SELECT state FROM calls ORDER BY created')]==['unknown','succeeded']


def test_midstream_never_retried(service,tmp_path):
    with service(fail_after_chunks=1) as (app,url):
        cfg,store,gateway=setup(tmp_path,url)
        with pytest.raises(ModelError,match='stream_error'): asyncio.run(gateway.generate(rid(store),MESSAGES))
        assert app.state.count==1
        with store.connect() as db:
            row=db.execute('SELECT * FROM calls').fetchone()
            assert row['state']=='unknown' and row['tokens_in'] is None


def test_429_persisted_cooldown_and_no_retry_storm(service,tmp_path):
    with service() as (app,url):
        app.state.profile.rpm=1
        cfg,store,gateway=setup(tmp_path,url,model_wait_budget=.02)
        asyncio.run(gateway.generate(rid(store),MESSAGES))
        with pytest.raises(ModelError) as error: asyncio.run(gateway.generate(rid(store),MESSAGES))
        assert error.value.status==429 and app.state.count==2
        recreated=Gateway(cfg,Store(store.path))
        with pytest.raises(ModelError,match='provider_cooldown'): asyncio.run(recreated.generate(rid(store),MESSAGES))
        assert app.state.count==2


@pytest.mark.parametrize('deadline,timeout,code',[(1,.02,'transport_timeout'),(.03,1,'model_deadline')])
def test_slow_provider_bounded_and_conservative(service,tmp_path,deadline,timeout,code):
    with service() as (app,url):
        app.state.profile.first_delay=.2
        cfg,store,gateway=setup(tmp_path,url,model_deadline=deadline,model_timeout=timeout,model_max_attempts=1)
        with pytest.raises(ModelError,match=code): asyncio.run(gateway.generate(rid(store),MESSAGES))
        assert gateway.pending==0 and gateway.slots._value==cfg.model_concurrency
        with store.connect() as db: assert db.execute('SELECT state FROM calls').fetchone()[0]=='unknown'


def test_cancellation_and_queue_deadline_release_slots(service,tmp_path):
    with service() as (app,url):
        app.state.profile.first_delay=.2
        cfg,store,gateway=setup(tmp_path,url,model_concurrency=1,model_wait_budget=.03)
        async def run():
            active=asyncio.create_task(gateway.generate(rid(store),MESSAGES))
            while not app.state.count: await asyncio.sleep(.005)
            with pytest.raises(ModelError,match='model_queue_deadline'): await gateway.generate(rid(store),MESSAGES)
            active.cancel()
            with pytest.raises(asyncio.CancelledError): await active
            assert gateway.slots._value==1 and gateway.pending==0
        asyncio.run(run())
        with store.connect() as db:
            rows=db.execute('SELECT state FROM calls').fetchall()
            assert len(rows)==1 and rows[0][0]=='unknown'


def test_retry_backoff_releases_slot_for_other_request(service,tmp_path):
    with service(fail_first_requests=1) as (app,url):
        cfg,store,gateway=setup(tmp_path,url,model_concurrency=1,retry_base_delay=.2)
        first,second=rid(store),rid(store)
        async def run():
            pending=asyncio.create_task(gateway.generate(first,MESSAGES))
            while True:
                with store.connect() as db:
                    logged=db.execute("SELECT 1 FROM events WHERE event='retry_scheduled'").fetchone()
                if logged: break
                await asyncio.sleep(.005)
            await gateway.generate(second,MESSAGES)
            assert not pending.done()
            await pending
        asyncio.run(run())
        received=[e['request_id'] for e in app.state.observed if e['event']=='standin_received']
        assert received==[first,second,first]


def test_real_stream_delivery_and_worker_queue_slowdown(service,tmp_path):
    with service(workers=1,load_factor=0) as (app,url):
        # Windows asyncio timers may coalesce sleeps below one timer tick.
        app.state.profile.first_delay=.08; app.state.profile.chunk_delay=.05
        cfg,store,gateway=setup(tmp_path,url)
        async def read(request):
            observed=[]
            async for event in HTTPBackend(cfg).stream(request,MESSAGES,1024):
                    if event.kind=='content': observed.append(time.perf_counter())
            return observed
        async def run(): return await asyncio.gather(read('first'),read('second'))
        times=asyncio.run(run())
        assert all(len(t)>1 and t[-1]-t[0]>.02 for t in times),(times,list(app.state.observed))
        starts=[e for e in app.state.observed if e['event']=='standin_worker_started']
        assert len(starts)==2 and max(e['queue_ms'] for e in starts)>20


def test_local_quota_blocks_before_http(service,tmp_path):
    with service() as (app,url):
        cfg,store,gateway=setup(tmp_path,url)
        cfg.groq_rpm=1
        asyncio.run(gateway.generate(rid(store),MESSAGES))
        with pytest.raises(ModelError,match='local_quota_minute'): asyncio.run(gateway.generate(rid(store),MESSAGES))
        assert app.state.count==1


def test_retry_exhaustion_is_three_attempts(service,tmp_path):
    with service(failure_rate=1) as (app,url):
        cfg,store,gateway=setup(tmp_path,url,retry_base_delay=.01)
        with pytest.raises(ModelError,match='provider_http_error'): asyncio.run(gateway.generate(rid(store),MESSAGES))
        assert app.state.count==3


def test_truncated_completion_is_not_regenerated(service,tmp_path):
    with service() as (app,url):
        cfg,store,gateway=setup(tmp_path,url)
        with pytest.raises(ModelError,match='incomplete_response'): asyncio.run(gateway.generate(rid(store),MESSAGES,cap=1))
        assert app.state.count==1


def test_queue_capacity_rejects_without_dispatch(service,tmp_path):
    with service() as (app,url):
        app.state.profile.first_delay=.2
        cfg,store,gateway=setup(tmp_path,url,model_concurrency=1,model_queue_limit=1)
        async def run():
            tasks=[asyncio.create_task(gateway.generate(rid(store),MESSAGES)) for _ in range(2)]
            while gateway.pending<2: await asyncio.sleep(.005)
            with pytest.raises(ModelError,match='model_queue_full'): await gateway.generate(rid(store),MESSAGES)
            await asyncio.gather(*tasks)
        asyncio.run(run())
        assert app.state.count==2
