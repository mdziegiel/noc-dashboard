"""Proxmox VE collector."""
import urllib.parse
from .utils import jget, service_url


def _auth(E):
    tid = E.get("PROXMOX_TOKEN_ID", "")
    if "!" not in tid and "@pam" in tid:
        tid = tid.replace("@pam", "@pam!")
    return {"Authorization": f"PVEAPIToken={tid}={E.get('PROXMOX_TOKEN_SECRET', '')}"}


def collect(E, card_cfg=None):
    d = {"state": "ok", "vms_running": 0, "vms_total": 0, "cpu": 0.0,
         "mem_used": 0.0, "mem_total": 0.0, "node": "?", "uptime_d": 0,
         "down_vms": [], "storage": []}
    auth = _auth(E)
    base = service_url(E.get("PROXMOX_HOST", "10.10.10.251"), "https", 8006) + "/api2/json"
    nodes = jget(f"{base}/nodes", auth)["data"]
    node = None
    for n in nodes:
        node = n["node"]
        d["node"] = node
        d["cpu"] = round(n.get("cpu", 0) * 100, 1)
        d["mem_used"] = round(n.get("mem", 0) / 1e9, 1)
        d["mem_total"] = round(n.get("maxmem", 1) / 1e9, 1)
        d["uptime_d"] = int(n.get("uptime", 0)) // 86400
    vms = jget(f"{base}/nodes/{node}/qemu", auth)["data"]
    if vms:
        run = [v for v in vms if v.get("status") == "running"]
        d["vms_running"] = len(run)
        d["vms_total"] = len(vms)
        d["down_vms"] = sorted(
            f"{v['vmid']} {v.get('name', '')}".strip()
            for v in vms if v.get("status") != "running")
        if d["down_vms"]:
            d["state"] = "warn"
    else:
        d["state"] = "degraded"
        d["note"] = "no VMs visible (check token ACL)"
    st = jget(f"{base}/nodes/{node}/storage", auth)["data"]
    cfg = card_cfg or {}
    warn_pct = cfg.get("thresholds", {}).get("storage_warn", 80)
    crit_pct = cfg.get("thresholds", {}).get("storage_critical", 90)
    for s in st:
        if not s.get("total"):
            continue
        used, tot = s.get("used", 0), s.get("total", 1)
        pct = round(100 * used / tot, 1)
        d["storage"].append({"name": s["storage"], "pct": pct,
                              "used_g": round(used / 1e9, 1),
                              "total_g": round(tot / 1e9, 1)})
    d["storage"].sort(key=lambda x: -x["pct"])
    if any(s["pct"] >= crit_pct for s in d["storage"]):
        d["state"] = "crit"
    elif any(s["pct"] >= warn_pct for s in d["storage"]) and d["state"] == "ok":
        d["state"] = "warn"
    return d


def collect_storage(E, card_cfg=None):
    """Proxmox storage only — for the proxmox_storage card type."""
    auth = _auth(E)
    base = service_url(E.get("PROXMOX_HOST", "10.10.10.251"), "https", 8006) + "/api2/json"
    nodes = jget(f"{base}/nodes", auth)["data"]
    node = nodes[0]["node"] if nodes else "proxmox"
    st = jget(f"{base}/nodes/{urllib.parse.quote(node)}/storage", auth)["data"]
    storage = []
    for s in st:
        if not s.get("total"):
            continue
        used, tot = s.get("used", 0), s.get("total", 1)
        pct = round(100 * used / tot, 1)
        storage.append({"name": s["storage"], "pct": pct,
                        "used_g": round(used / 1e9, 1),
                        "total_g": round(tot / 1e9, 1)})
    storage.sort(key=lambda x: -x["pct"])
    state = "ok"
    if any(s["pct"] >= 90 for s in storage):
        state = "crit"
    elif any(s["pct"] >= 80 for s in storage):
        state = "warn"
    return {"state": state, "storage": storage}
