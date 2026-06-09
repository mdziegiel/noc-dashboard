"""Wazuh SIEM + indexer collector."""
import re
from .utils import jget, req, b64


def collect(E, card_cfg=None):
    d = {"state": "ok", "active": 0, "total": 0, "down": []}
    jwt = req(
        "https://10.10.10.233:55000/security/user/authenticate?raw=true",
        {"Authorization": "Basic " + b64(
            f"{E.get('WAZUH_API_USER', 'hermes')}:{E.get('WAZUH_API_PASSWORD', '')}")}).strip()
    ag = jget("https://10.10.10.233:55000/agents?limit=500",
               {"Authorization": f"Bearer {jwt}"})["data"]["affected_items"]
    d["total"] = len(ag)
    d["active"] = sum(1 for a in ag if a.get("status") == "active")
    d["down"] = [f"{a.get('id')} {a.get('name', '')}".strip()
                 for a in ag if a.get("status") != "active"]
    if d["down"]:
        d["state"] = "warn"
    iu = E.get("WAZUH_INDEXER_USER", "").strip()
    ip = E.get("WAZUH_INDEXER_PASS", "").strip()
    if iu and ip:
        ix = E.get("WAZUH_INDEXER_HOST", "https://10.10.10.233:9200").rstrip("/")
        try:
            q = {"size": 0,
                 "query": {"bool": {"filter": [
                     {"range": {"@timestamp": {"gte": "now-24h"}}}]}},
                 "aggs": {"hi": {"filter": {"range": {"rule.level": {"gte": 12}}}}}}
            res = jget(f"{ix}/wazuh-alerts-*/_search",
                       {"Authorization": "Basic " + b64(f"{iu}:{ip}")}, data=q, method="POST")
            tot = res.get("hits", {}).get("total", {})
            d["alerts_24h"] = tot.get("value", tot) if isinstance(tot, dict) else tot
            d["high_24h"] = res.get("aggregations", {}).get("hi", {}).get("doc_count", 0)
            cfg = card_cfg or {}
            thresh = cfg.get("thresholds", {}).get("high_alert_warn", 1)
            if d["high_24h"] >= thresh:
                d["state"] = "crit"
        except Exception as e:
            d["alerts_err"] = type(e).__name__
    return d
