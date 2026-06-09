"""AdGuard Home collector."""
from .utils import jget, b64


def collect(E, card_cfg=None):
    d = {"state": "ok", "queries": 0, "blocked": 0, "block_pct": 0.0, "avg_ms": 0.0}
    url = E.get("ADGUARD_URL", "http://10.10.10.21").rstrip("/")
    user = E.get("ADGUARD_USERNAME", "mdziegiel")
    pw = E.get("ADGUARD_PASSWORD", "")
    if not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "ADGUARD_PASSWORD not set",
                "queries": 0, "blocked": 0, "block_pct": 0.0, "avg_ms": 0.0}
    s = jget(f"{url}/control/stats",
             {"Authorization": "Basic " + b64(f"{user}:{pw}")})
    tot = s.get("num_dns_queries", 0)
    blk = s.get("num_blocked_filtering", 0)
    d["queries"] = tot
    d["blocked"] = blk
    d["block_pct"] = round(100 * blk / tot, 1) if tot else 0.0
    d["avg_ms"] = round(s.get("avg_processing_time", 0) * 1000, 1)
    return d
