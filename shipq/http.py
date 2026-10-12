from curl_cffi import requests

from .models import ShipError

_session = requests.Session(impersonate="chrome", timeout=30)


def get(url: str, **kw):
    try:
        return _session.get(url, **kw)
    except requests.RequestsError as e:
        raise ShipError(f"{url}: {e}") from e


def post(url: str, **kw):
    try:
        return _session.post(url, **kw)
    except requests.RequestsError as e:
        raise ShipError(f"{url}: {e}") from e
