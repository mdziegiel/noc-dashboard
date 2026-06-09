"""Proxmox Backup Server collector."""
import time
import urllib.parse
from .utils import jget


def collect(E, card_cfg=None):
    d = {"state": "ok", "ok": 0, "fail": 0, "run": 0, "last_backup": "?", "datastores": []}
    cfg = card_cfg or {}
    warn_hours = cfg.get("thresholds", {}).get("last_backup_warn_hours", 26)
    base = E.get("PBS_URL", "https://10.10.10.77:8007").rstrip("/")
    user = E.get("PBS_USERNAME", "root@pam")
    pw = E.get("PBS_PASSWORD", "")
    if not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "PBS_PASSWORD not set",
                "ok": 0, "fail": 0, "run": 0, "last_backup": "?", "datastores": []}
    tk = jget(f"{base}/api2/json/access/ticket",
              data=urllib.parse.urlencode({"username": user, "password": pw}),
              headers={"Content-Type": "application/x-www-form-urlencoded"},
              method="POST")["data"]["ticket"]
    cookie = {"Cookie": f"PBSAuthCookie={urllib.parse.quote(tk, safe='')}"}
    since = int(time.time()) - 86400
    tasks = jget(f"{base}/api2/json/nodes/localhost/tasks?since={since}&limit=500", cookie)["data"]
    last_backup_epoch = 0
    for t in tasks:
        s = t.get("status", "running")
        wt = t.get("worker_type", "")
        if s == "running" or "endtime" not in t:
            d["run"] += 1
        elif s == "OK":
            d["ok"] += 1
            if wt == "backup" and t.get("endtime", 0) > last_backup_epoch:
                last_backup_epoch = t.get("endtime", 0)
        else:
            d["fail"] += 1
    if last_backup_epoch:
        ago_h = (time.time() - last_backup_epoch) / 3600
        d["last_backup"] = (f"{ago_h:.1f}h ago" if ago_h < 48 else f"{ago_h/24:.1f}d ago")
        if ago_h > warn_hours:
            d["state"] = "warn"
    else:
        d["last_backup"] = "none in 24h"
        d["state"] = "warn"
    if d["fail"]:
        d["state"] = "crit"
    try:
        dss = jget(f"{base}/api2/json/status/datastore-usage", cookie)["data"]
        for ds in dss:
            tot = ds.get("total", 0) or 0
            used = ds.get("used", 0) or 0
            pct = round(100 * used / tot, 1) if tot else 0
            d["datastores"].append({"name": ds.get("store", "?"), "pct": pct})
    except Exception:
        pass
    return d
