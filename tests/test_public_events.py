from concurrent.futures import ThreadPoolExecutor
from relay.store import Store
from relay import pagination
import pytest


def test_cancel_finalize_race_has_exactly_one_done(tmp_path):
    store=Store(tmp_path/'db')
    for i in range(20):
        rid,_=store.create(str(i),'hash',{'question':'test'})
        with ThreadPoolExecutor(2) as pool:
            outcomes=list(pool.map(lambda status:store.update(rid,status,{'answer':'validated','citations':[]}),['answered','cancelled']))
        assert sum(outcomes)==1
        rows=store.public_events(rid)
        assert sum(r['event']=='done' for r in rows)==1
        if store.get(rid)['status']=='cancelled': assert not any(r['event']=='answer_delta' for r in rows)


def test_failed_publication_rolls_back_terminal(tmp_path):
    store=Store(tmp_path/'db'); rid,_=store.create('k','h',{'question':'test'})
    with pytest.raises(ValueError): store.update(rid,'needs_clarification',{'message':'x'*9000})
    assert store.get(rid)['status']=='queued'
    assert len(store.public_events(rid))==1


def test_cursor_scope_and_expiry(monkeypatch):
    value=pagination.encode(b'key',[1,'id'],'requests')
    with pytest.raises(ValueError): pagination.decode(b'key',value,'runs')
    monkeypatch.setattr(pagination.time,'time',lambda:10**12)
    with pytest.raises(ValueError): pagination.decode(b'key',value,'requests')
