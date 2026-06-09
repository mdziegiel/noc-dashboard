"""SMART disk health via Proxmox API."""
import re
import urllib.parse
from .utils import jget, service_url


def _smart_raw_int(v):
    m = re.search(r"-?\d+", str(v or ""))
    return int(m.group(0)) if m else 0


def collect(E, card_cfg=None):
    d = {"state": "ok", "checked": 0, "passed": 0, "warn": 0, "fail": 0,
         "prefail": 0, "problems": [], "disks": [], "vm_disks": 0}
    tid = E.get("PROXMOX_TOKEN_ID", "")
    if "!" not in tid and "@pam" in tid:
        tid = tid.replace("@pam", "@pam!")
    auth = {"Authorization": f"PVEAPIToken={tid}={E.get('PROXMOX_TOKEN_SECRET', '')}"}
    base = service_url(E.get("PROXMOX_HOST", "10.10.10.251"), "https", 8006) + "/api2/json"
    nodes = jget(f"{base}/nodes", auth).get("data", [])
    if not nodes:
        return {**d, "state": "degraded", "note": "no Proxmox nodes visible"}
    CRITICAL = ("realloc", "pending", "uncorrect", "offline_uncorrect", "reported_uncorrect",
                "command_timeout", "media_wearout", "media_and_data_integrity")
    for n in nodes:
        node = n.get("node")
        if not node:
            continue
        try:
            vms = jget(f"{base}/nodes/{urllib.parse.quote(node)}/qemu", auth).get("data", [])
            for vm in vms:
                try:
                    cfg = jget(f"{base}/nodes/{urllib.parse.quote(node)}/qemu/{vm.get('vmid')}/config", auth).get("data", {})
                    d["vm_disks"] += sum(1 for k in cfg if re.match(r"^(ide|sata|scsi|virtio)\d+$", k))
                except Exception:
                    pass
        except Exception:
            pass
        disks = jget(f"{base}/nodes/{urllib.parse.quote(node)}/disks/list", auth).get("data", [])
        for disk in disks:
            dev = disk.get("devpath")
            if not dev:
                continue
            rec = {"node": node, "dev": dev, "model": (disk.get("model") or disk.get("serial") or dev)[:26],
                   "health": disk.get("health") or "UNKNOWN", "issues": []}
            d["checked"] += 1
            health = str(rec["health"]).upper()
            if health in ("PASSED", "OK", "GOOD"):
                d["passed"] += 1
            elif health in ("UNKNOWN", "N/A", ""):
                d["warn"] += 1
                rec["issues"].append("SMART health unknown")
            else:
                d["fail"] += 1
                rec["issues"].append(f"SMART health {rec['health']}")
            try:
                url = f"{base}/nodes/{urllib.parse.quote(node)}/disks/smart?disk={urllib.parse.quote(dev, safe='')}"
                sm = jget(url, auth).get("data", {})
                txt = sm.get("text", "") or ""
                for a in (sm.get("attributes", []) or []):
                    name = str(a.get("name", ""))
                    fail = str(a.get("fail", "-")).strip()
                    flags = str(a.get("flags", ""))
                    raw = _smart_raw_int(a.get("raw"))
                    if flags.startswith("P") or flags.startswith("PO"):
                        d["prefail"] += 1
                    lname = name.lower()
                    if fail and fail != "-":
                        rec["issues"].append(f"{name} {fail}")
                    elif raw > 0 and any(x in lname for x in CRITICAL):
                        rec["issues"].append(f"{name} raw={raw}")
                m2 = re.search(r"Critical Warning:\s*(0x[0-9a-fA-F]+|\d+)", txt)
                if m2 and int(m2.group(1), 0) != 0:
                    rec["issues"].append(f"NVMe critical warning {m2.group(1)}")
            except Exception as e:
                d["warn"] += 1
                rec["issues"].append(f"SMART detail unavailable: {type(e).__name__}")
            if rec["issues"]:
                d["problems"].append(f"{rec['model']} {dev}: " + "; ".join(rec["issues"][:3]))
            d["disks"].append(rec)
    if not d["checked"]:
        d["state"] = "degraded"
        d["note"] = "no SMART-capable disks returned"
    elif d["fail"] or any("raw=" in p or "critical" in p.lower() for p in d["problems"]):
        d["state"] = "crit"
    elif d["warn"] or d["problems"]:
        d["state"] = "warn"
    return d
