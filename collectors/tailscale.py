"""Tailscale collector."""
import datetime
from .utils import jget


def collect(E, card_cfg=None):
    token = E.get("TAILSCALE_API_KEY", "").strip()
    if not token or token.startswith("<"):
        return {"state": "degraded", "note": "Tailscale API key not set",
                "total": 0, "online": 0, "devices": []}
    d = {"state": "ok", "total": 0, "online": 0, "offline": 0,
         "exit_nodes": [], "devices": [], "soonest_expiry_days": None}
    j = jget("https://api.tailscale.com/api/v2/tailnet/-/devices",
             {"Authorization": f"Bearer {token}"})
    devs = j.get("devices", [])
    d["total"] = len(devs)
    now = datetime.datetime.now(datetime.UTC)
    soonest = None
    warn_days = (card_cfg or {}).get("thresholds", {}).get("key_expiry_warn_days", 30)
    for dev in devs:
        ls = dev.get("lastSeen", "")
        online = False
        if ls:
            try:
                t = datetime.datetime.strptime(ls, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
                online = (now - t).total_seconds() < 300
            except Exception:
                pass
        if online: d["online"] += 1
        else: d["offline"] += 1
        if dev.get("exitNodeOption"):
            d["exit_nodes"].append(dev.get("hostname", "?"))
        if not dev.get("keyExpiryDisabled") and dev.get("expires"):
            try:
                ex = datetime.datetime.strptime(dev["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)
                days = (ex - now).total_seconds() / 86400
                if days > -3650 and (soonest is None or days < soonest):
                    soonest = days
            except Exception:
                pass
        d["devices"].append({
            "name": dev.get("hostname", dev.get("name", "?")),
            "os": dev.get("os", "?"),
            "online": online,
            "exit_node": bool(dev.get("exitNodeOption")),
        })
    d["devices"].sort(key=lambda x: (not x["online"], x["name"].lower()))
    if soonest is not None:
        d["soonest_expiry_days"] = int(soonest)
        if soonest < warn_days:
            d["state"] = "warn"
    return d
