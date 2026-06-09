"""
Shared utilities for all NOC Dashboard collectors.
All HTTP is done with stdlib only — no requests dependency in collectors.
"""
import base64
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import http.cookiejar

TIMEOUT = 15

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def req(url, headers=None, data=None, method=None, cookiejar=None):
    h = dict(headers or {})
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        data = data.encode()
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    if cookiejar is not None:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=CTX),
            urllib.request.HTTPCookieProcessor(cookiejar))
        resp = opener.open(r, timeout=TIMEOUT)
    else:
        resp = urllib.request.urlopen(r, timeout=TIMEOUT, context=CTX)
    return resp.read().decode("utf-8", "replace")


def jget(url, headers=None, data=None, method=None, cookiejar=None):
    return json.loads(req(url, headers, data, method, cookiejar))


def service_url(host_or_url, scheme="https", port=None):
    raw = str(host_or_url or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if port is not None and ":" not in raw:
        raw = f"{raw}:{port}"
    return f"{scheme}://{raw}"
