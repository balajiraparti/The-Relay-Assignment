"""Bounded, fail-visible JSONL telemetry. Never pass raw content to event fields."""
import contextvars
import json
import logging
import logging.handlers
import queue
import re
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

_context = contextvars.ContextVar('relay_trace', default={})
_active = contextvars.ContextVar('relay_telemetry', default=None)
SENSITIVE = {'authorization','api_key','groq_api_key','password','secret','token','question',
             'query','answer','prompt','messages','content','body','response','reasoning','exception'}


def redact(value, secrets=()):
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if any(part in str(k).lower().replace('-', '_').split('_') for part in ('password','secret','authorization')) or str(k).lower() in SENSITIVE
                else ('[REDACTED]' if str(k).lower().replace('-', '_').endswith('api_key') else redact(v, secrets)) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [redact(v,secrets) for v in value]
    if isinstance(value,str):
        for secret in secrets:
            if secret: value=value.replace(secret,'[REDACTED]')
        value=re.sub(r'(?i)Bearer\s+[^\s,;]+|\b(?:gsk_|sk-)[A-Za-z0-9_-]+','[REDACTED]',value)
        return value[:4096]
    if value is None or isinstance(value,(bool,int,float)): return value
    return '[UNSUPPORTED]'


@contextmanager
def trace(**fields):
    token=_context.set({**_context.get(),**fields})
    try: yield
    finally: _context.reset(token)


class TelemetryError(RuntimeError): pass


class StrictQueueHandler(logging.handlers.QueueHandler):
    def enqueue(self, record): self.queue.put_nowait(record)
    def handleError(self, record): raise TelemetryError('telemetry_queue_full') from None


class Telemetry:
    def __init__(self, directory, *, service='app', secrets=(), capacity=10000,
                 segment_bytes=10_000_000, max_bytes=50_000_000):
        if min(capacity,segment_bytes,max_bytes)<=0: raise ValueError('invalid_telemetry_capacity')
        self.directory=Path(directory); self.directory.mkdir(parents=True,exist_ok=True)
        self.service=service; self.run_id=uuid.uuid4().hex; self.secrets=tuple(secrets)
        self.queue=queue.Queue(capacity); self.handler=StrictQueueHandler(self.queue)
        self.start=time.perf_counter(); self.sequence=0; self.lock=threading.Lock()
        self.failed=False; self.closed=False; self.dropped_debug=0
        self.segment_bytes=segment_bytes; self.max_bytes=max_bytes
        self.thread=threading.Thread(target=self._write,name='relay-telemetry',daemon=True)
        self.thread.start()

    def _fail(self):
        self.failed=True
        sys.stderr.write('Relay telemetry incomplete: writer/queue failure; admission must stop.\n')
        try: (self.directory/f'{self.service}.{self.run_id}.incomplete').touch()
        except OSError: pass

    def emit(self, name, *, request_id=None, level='INFO', **fields):
        with self.lock:
            if self.failed or self.closed: raise TelemetryError('telemetry_unavailable')
            self.sequence+=1
            context={**_context.get()}
            if request_id is not None: context['request_id']=request_id
            event=redact({'schema_version':1,'event_id':uuid.uuid4().hex,'event_name':name,
                'timestamp_utc':datetime.now(timezone.utc).isoformat(),
                'elapsed_ms':(time.perf_counter()-self.start)*1000,'level':level,
                'run_id':self.run_id,'service':self.service,'sequence':self.sequence,
                **context,'attributes':fields},self.secrets)
            record=logging.LogRecord('relay',getattr(logging,level),__file__,0,
                                     json.dumps(event,allow_nan=False),(),None)
            try: self.handler.handle(record)
            except TelemetryError:
                if level=='DEBUG':
                    self.dropped_debug+=1
                    sys.stderr.write('Relay telemetry DEBUG event dropped.\n')
                    return
                self._fail(); raise

    @contextmanager
    def span(self,name,**fields):
        parent=_context.get().get('span_id'); start=time.perf_counter()
        with trace(span_id=uuid.uuid4().hex,parent_span_id=parent):
            self.emit(name+'_started',**fields)
            try: yield
            except BaseException:
                self.emit(name+'_finished',outcome='failed',duration_ms=(time.perf_counter()-start)*1000)
                raise
            else: self.emit(name+'_finished',outcome='succeeded',duration_ms=(time.perf_counter()-start)*1000)

    def _write(self):
        stream=None; total=0; size=0; segment=0
        try:
            while True:
                record=self.queue.get()
                try:
                    if record is None: return
                    if self.failed: continue
                    data=(record.getMessage()+'\n').encode('utf-8')
                    if total+len(data)>self.max_bytes: raise OSError('telemetry_storage_limit')
                    if stream is None or size+len(data)>self.segment_bytes:
                        if stream: stream.close()
                        stream=(self.directory/f'{self.service}.{self.run_id}.{segment:04d}.jsonl').open('xb')
                        segment+=1; size=0
                    stream.write(data); stream.flush(); size+=len(data); total+=len(data)
                except (OSError,ValueError): self._fail()
                finally: self.queue.task_done()
        finally:
            if stream: stream.close()

    def close(self):
        with self.lock:
            if self.closed: return
            self.closed=True
        self.queue.put(None); self.thread.join()
        if self.failed: raise TelemetryError('telemetry_flush_incomplete')

    def __enter__(self):
        self.token=_active.set(self); self.emit('service_started'); return self

    def __exit__(self,*exc):
        try:
            if not self.failed: self.emit('service_stopped',dropped_debug=self.dropped_debug)
        finally:
            _active.reset(self.token); self.close()


def current(): return _active.get()
