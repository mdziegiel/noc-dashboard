"""CrowdSec collector."""
import json
from collections import Counter
from .utils import jget


def collect(E, card_cfg=None):
    d = {"state": "ok", "bans": 0, "local_bans": 0, "detections_24h": None, "top": []}
    apikey = E.get("CROWDSEC_API_KEY", "")
    apiurl = E.get("CROWDSEC_API_URL", "http://10.10.10.237:18080").rstrip("/")
    dec = jget(f"{apiurl}/v1/decisions", {"X-Api-Key": apikey})
    if isinstance(dec, list):
        d["bans"] = len(dec)
        local = [x for x in dec if x.get("origin") not in ("lists", "CAPI")]
        d["local_bans"] = len(local)
        scen = Counter(x.get("scenario", "?").split("/")[-1] for x in local)
        d["top"] = [[k, v] for k, v in scen.most_common(3) if k != "?"]
    mu = E.get("CROWDSEC_MACHINE_USER", "")
    mp = E.get("CROWDSEC_MACHINE_PASS", "")
    if mu and mp:
        try:
            tok = jget(f"{apiurl}/v1/watchers/login",
                       {"Content-Type": "application/json"},
                       json.dumps({"machine_id": mu, "password": mp}).encode(), "POST")["token"]
            alerts = jget(f"{apiurl}/v1/alerts?since=24h&limit=500",
                          {"Authorization": "Bearer " + tok})
            if isinstance(alerts, list):
                def is_local(a):
                    scope = (a.get("source", {}) or {}).get("scope", "") or ""
                    scen = a.get("scenario", "") or ""
                    return not scen.startswith("update :") and scope in ("Ip", "Range")
                d["detections_24h"] = sum(1 for a in alerts if is_local(a))
        except Exception:
            d["detections_24h"] = None
    return d
