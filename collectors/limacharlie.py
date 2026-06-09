"""LimaCharlie EDR collector."""
import base64
import gzip
import json
import time
import urllib.parse
import urllib.request
import zlib
from collections import Counter
from .utils import CTX, TIMEOUT, jget


def _get_jwt(api_key, oid):
    data = urllib.parse.urlencode({"secret": api_key, "oid": oid}).encode()
    r = urllib.request.Request("https://jwt.limacharlie.io", data=data,
                               headers={"Content-Type": "application/x-www-form-urlencoded"},
                               method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=TIMEOUT, context=CTX).read().decode())["jwt"]


def _unwrap(raw):
    if not raw:
        return []
    try:
        return json.loads(zlib.decompress(base64.b64decode(raw), 16 + zlib.MAX_WBITS).decode())
    except Exception:
        return []


def _env_first(E, *keys):
    for key in keys:
        val = str(E.get(key, "") or "").strip().strip('"').strip("'")
        if val and not val.startswith("<"):
            return val
    return ""


def collect(E, card_cfg=None):
    api_key = _env_first(E, "LIMACHARLIE_API_KEY", "LIMA_CHARLIE_API_KEY", "LC_API_KEY")
    oid = _env_first(E, "LIMACHARLIE_OID", "LIMACHARLIE_ORG_OID", "LIMA_CHARLIE_OID", "LC_OID")
    if not api_key or not oid:
        return {"state": "degraded", "note": "LimaCharlie creds not set",
                "total": 0, "online": 0, "offline": 0, "detections_24h": None, "top": [], "offline_hosts": []}
    jwt = _get_jwt(api_key, oid)
    auth = {"Authorization": f"Bearer {jwt}"}
    base = "https://api.limacharlie.io/v1"

    def get_all_sensors(online_only=False):
        sensors = []
        token = None
        for _ in range(20):
            qp = {"limit": "500"}
            if token: qp["continuation_token"] = token
            if online_only: qp["is_online_only"] = "true"
            url = f"{base}/sensors/{urllib.parse.quote(oid)}?{urllib.parse.urlencode(qp)}"
            res = jget(url, auth)
            sensors.extend(res.get("sensors", []))
            token = res.get("continuation_token")
            if not token: break
        return sensors

    all_sensors = get_all_sensors(False)
    online_sensors = get_all_sensors(True)
    total = len(all_sensors)
    online = len(online_sensors)
    online_sids = {str(s.get("sid", "")) for s in online_sensors if s.get("sid")}
    offline = max(0, total - online)
    offline_hosts = sorted(
        [s.get("hostname") or str(s.get("sid", ""))[:8] or "unknown"
         for s in all_sensors if str(s.get("sid", "")) not in online_sids])[:5]
    d = {"state": "ok", "total": total, "online": online, "offline": offline,
         "detections_24h": None, "top": [], "offline_hosts": offline_hosts}
    if total == 0:
        d["state"] = "degraded"; d["note"] = "no sensor data"
    elif offline:
        d["state"] = "warn"
    try:
        end = int(time.time())
        start = end - 86400
        detects = []
        cursor = "-"
        for _ in range(10):
            qp = {"start": str(start), "end": str(end), "cursor": cursor,
                  "is_compressed": "true", "limit": "200"}
            url = f"{base}/insight/{urllib.parse.quote(oid)}/detections?{urllib.parse.urlencode(qp)}"
            res = jget(url, auth)
            batch = _unwrap(res.get("detects", ""))
            if isinstance(batch, dict): batch = list(batch.values())
            detects.extend(batch or [])
            cursor = res.get("next_cursor")
            if not cursor: break
        d["detections_24h"] = len(detects)
        cats = Counter()
        for det in detects:
            cat = (det.get("detect", {}) or {}).get("detect", {}) or {}
            name = cat.get("name") or cat.get("type") or "unknown"
            cats[name] += 1
        d["top"] = [[k, v] for k, v in cats.most_common(3)]
        if d["detections_24h"] > 0 and d["state"] == "ok":
            d["state"] = "warn"
    except Exception as e:
        d["detections_note"] = f"Insight unavailable: {type(e).__name__}"
    return d
