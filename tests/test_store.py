import pytest
from relay.store import Store


def test_idempotent_and_terminal(tmp_path):
    s=Store(tmp_path/'test.db')
    rid,fresh=s.create('key','hash',{'question':'test'})
    assert fresh
    assert s.create('key','hash',{})==(rid,False)
    with pytest.raises(ValueError): s.create('key','different',{})
    assert s.update(rid,'answered',{'answer':'yes'})
    assert not s.update(rid,'cancelled')


def test_budget_persists_and_unknown_is_not_free(tmp_path):
    path=tmp_path/'test.db'; s=Store(path)
    s.operation('r')
    cid=s.reserve('r','groq',90,(10,100,10,100))
    s.call_state(cid,'unknown')
    with pytest.raises(ValueError): Store(path).reserve('r','groq',20,(10,100,10,100))
    s.call_state(cid,'succeeded',{'prompt_tokens':10,'completion_tokens':5})
    assert s.reserve('r','groq',20,(10,100,10,100))


def test_sources_isolated(tmp_path):
    s=Store(tmp_path/'test.db')
    s.operation('r')
    s.reserve('r','stand-in',100,(1,100,1,100))
    assert s.reserve('r','groq',100,(1,100,1,100))


def test_daily_budget_survives_restart_and_known_usage_is_idempotent(tmp_path):
    s=Store(tmp_path/'test.db'); s.operation('r')
    cid=s.reserve('r','groq',90,(10,100,10,100))
    s.call_state(cid,'dispatched')
    with s.connect() as db: db.execute('UPDATE calls SET created=created-61 WHERE id=?',(cid,))
    recreated=Store(s.path); recreated.recover()
    with pytest.raises(ValueError,match='local_quota_day'): recreated.reserve('r','groq',20,(10,100,10,100))
    with pytest.raises(ValueError,match='cannot_release'): recreated.call_state(cid,'released')
    for _ in range(2): recreated.call_state(cid,'succeeded',{'prompt_tokens':10,'completion_tokens':5})
    assert recreated.reserve('r','groq',80,(10,100,10,100))


def test_recovery_releases_only_unsent_reservations(tmp_path):
    s=Store(tmp_path/'test.db'); s.operation('r')
    unsent=s.reserve('r','groq',10,(10,100,10,100))
    sent=s.reserve('r','groq',10,(10,100,10,100)); s.call_state(sent,'dispatched')
    s.recover()
    with s.connect() as db: states={r['id']:r['state'] for r in db.execute('SELECT * FROM calls')}
    assert states=={unsent:'released',sent:'unknown'}
