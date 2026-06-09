"""AdGuard Home #2 collector — identical logic to adguard.py but uses ADGUARD2_* env keys."""
from .utils import jget, b64


def collect(E, card_cfg=None):
    url  = (E.get("ADGUARD2_URL") or "").rstrip("/")
    user = E.get("ADGUARD2_USERNAME", "")
    pw   = E.get("ADGUARD2_PASSWORD", "")
    if not url or not user or not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "ADGUARD2 creds not configured",
                "queries": 0, "blocked": 0, "block_pct": 0.0, "avg_ms": 0.0}
    d = {"state": "ok", "queries": 0, "blocked": 0, "block_pct": 0.0, "avg_ms": 0.0}
    try:
        s = jget(f"{url}/control/stats",
                 {"Authorization": "Basic " + b64(f"{user}:{pw}")})
        tot = s.get("num_dns_queries", 0)
        blk = s.get("num_blocked_filtering", 0)
        d["queries"]   = tot
        d["blocked"]   = blk
        d["block_pct"] = round(100 * blk / tot, 1) if tot else 0.0
        d["avg_ms"]    = round(s.get("avg_processing_time", 0) * 1000, 1)
    except Exception as e:
        return {"state": "error", "note": f"{type(e).__name__}: {str(e)[:140]}",
                "queries": 0, "blocked": 0, "block_pct": 0.0, "avg_ms": 0.0}
    return d
