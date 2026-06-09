"""WGDashboard collector.

Auth: POST /api/authenticate  → cookie-based session
Data: GET  /api/getWireguardConfigurations  → list of configs with ConnectedPeers/TotalPeers/Status

Requires: WGDASHBOARD_URL, WGDASHBOARD_USERNAME, WGDASHBOARD_PASSWORD
"""
import json
import ssl
import urllib.request
import urllib.parse
import http.cookiejar
from .utils import TIMEOUT

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def collect(E, card_cfg=None):
    base = (E.get("WG_URL") or E.get("WGDASHBOARD_URL") or "").rstrip("/")
    user = (E.get("WG_USERNAME") or E.get("WGDASHBOARD_USERNAME") or "").strip()
    pw   = (E.get("WG_PASSWORD") or E.get("WGDASHBOARD_PASSWORD") or "").strip()
    empty = {"connected": 0, "total_peers": 0, "ifaces_up": 0, "ifaces_total": 0, "interfaces": []}

    if not base or not user or not pw or pw.startswith("<"):
        return {**empty, "state": "degraded", "note": "WGDashboard creds not set"}

    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=CTX),
            urllib.request.HTTPCookieProcessor(cj),
        )

        def call(path, data=None, method="GET"):
            headers = {}
            if isinstance(data, dict):
                data = json.dumps(data).encode()
                headers["Content-Type"] = "application/json"
            req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
            return json.loads(opener.open(req, timeout=TIMEOUT).read().decode("utf-8", "replace"))

        auth = call("/api/authenticate", {"username": user, "password": pw}, "POST")
        if not auth.get("status"):
            return {**empty, "state": "error",
                    "note": "Auth failed: " + str(auth.get("message", ""))[:80]}

        confs = call("/api/getWireguardConfigurations").get("data", [])
        d = {"state": "ok", "connected": 0, "total_peers": 0,
             "ifaces_up": 0, "ifaces_total": len(confs), "interfaces": []}

        for c in confs:
            up = bool(c.get("Status"))
            cp = int(c.get("ConnectedPeers", 0) or 0)
            tp = int(c.get("TotalPeers", 0) or 0)
            d["connected"]   += cp
            d["total_peers"] += tp
            if up:
                d["ifaces_up"] += 1
            d["interfaces"].append({
                "name": c.get("Name", "?"), "up": up,
                "connected": cp, "total": tp,
                "addr": c.get("Address", "?"),
            })

        d["interfaces"].sort(key=lambda x: x["name"])
        if d["ifaces_total"] and d["ifaces_up"] < d["ifaces_total"]:
            d["state"] = "warn"
        return d

    except Exception as e:
        return {**empty, "state": "error", "note": f"{type(e).__name__}: {str(e)[:140]}"}
