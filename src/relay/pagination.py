"""Signed, expiring cursors bound to one collection/filter set."""
import base64
import hashlib
import hmac
import json
import time


def encode(secret,position,scope,snapshot=None):
    data={'v':1,'position':position,'scope':scope,'snapshot':snapshot or time.time(),'expires':time.time()+3600}
    raw=base64.urlsafe_b64encode(json.dumps(data,separators=(',',':')).encode()).decode()
    return raw+'.'+hmac.new(secret,raw.encode(),hashlib.sha256).hexdigest()


def decode(secret,cursor,scope):
    try:
        if len(cursor)>2048: raise ValueError()
        raw,signature=cursor.split('.')
        if not hmac.compare_digest(hmac.new(secret,raw.encode(),hashlib.sha256).hexdigest(),signature): raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(raw))
        if data['v']!=1 or data['scope']!=scope or data['expires']<time.time(): raise ValueError()
        return data
    except Exception:
        raise ValueError('invalid_cursor') from None
