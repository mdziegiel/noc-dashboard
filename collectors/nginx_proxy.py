"""Nginx Proxy Manager collector."""
import time
from .utils import jget


def collect(E, card_cfg=None):
    base = E.get("NPM_URL", "").strip().rstrip("/")
    email = E.get("NPM_EMAIL", "").strip()
    pw = E.get("NPM_PASSWORD", "").strip()
    if not base or not email or not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "NPM creds not set",
                "hosts": 0, "enabled": 0, "disabled": 0, "certs": 0, "problems": []}
    d = {"state": "ok", "hosts": 0, "enabled": 0, "disabled": 0,
         "errored": 0, "certs": 0, "certs_expiring": 0, "problems": [], "cert_list": []}
    tok = jget(f"{base}/api/tokens",
               data={"identity": email, "secret": pw}, method="POST").get("token")
    if not tok:
        raise RuntimeError("NPM auth returned no token")
    auth = {"Authorization": f"Bearer {tok}"}
    hosts = jget(f"{base}/api/nginx/proxy-hosts", auth)
    d["hosts"] = len(hosts)
    for h in hosts:
        nm = (h.get("domain_names") or ["?"])[0]
        if not h.get("enabled"):
            d["disabled"] += 1
            d["problems"].append(f"disabled: {nm}")
        else:
            d["enabled"] += 1
        meta = h.get("meta") or {}
        if meta.get("nginx_online") is False or meta.get("nginx_err"):
            d["errored"] += 1
            d["problems"].append(f"ERROR {nm}: {str(meta.get('nginx_err') or 'offline')[:50]}")
    try:
        certs = jget(f"{base}/api/nginx/certificates", auth)
        d["certs"] = len(certs)
        now = time.time()
        warn_days = (card_cfg or {}).get("thresholds", {}).get("cert_warn_days", 14)
        for c in certs:
            exp = c.get("expires_on")
            if not exp: continue
            nm = (c.get("domain_names") or [c.get("nice_name") or "?"])[0]
            try:
                ep = time.mktime(time.strptime(exp[:19], "%Y-%m-%dT%H:%M:%S"))
                days = int((ep - now) / 86400)
                d["cert_list"].append({"name": nm, "days": days})
                if days <= warn_days:
                    d["certs_expiring"] += 1
                    d["problems"].append(f"cert expiring: {c.get('nice_name') or nm}")
            except Exception:
                pass
        d["cert_list"].sort(key=lambda x: x["days"])
    except Exception:
        pass
    if d["errored"]:
        d["state"] = "crit"
    elif d["disabled"] or d["certs_expiring"]:
        d["state"] = "warn"
    return d
