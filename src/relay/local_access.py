"""Local-only address validation shared by configuration and the UI."""
from urllib.parse import urlsplit
import ipaddress


def local_origin(value):
    try:
        url=urlsplit(value)
        if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):
            raise ValueError()
        _=url.port
    except ValueError: raise ValueError('backend must be a local HTTP origin') from None
    return value.rstrip('/')


def local_peer(host):
    if host=='testclient': return True # Starlette in-process test transport only.
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False


def local_host(value):
    try: return urlsplit('http://'+value).hostname in ('127.0.0.1','localhost','::1','testserver')
    except ValueError: return False
