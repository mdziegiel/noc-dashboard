"""Uptime Kuma collector — per-monitor SQLite via Portainer exec."""
import re
import urllib.parse
from .utils import jget, req, b64


def collect(E, card_cfg=None):
    d = {"state": "ok", "up": 0, "total": 0, "down": [], "other": [], "certs": []}
    base = E.get("UPTIME_KUMA_URL", "").strip().rstrip("/")
    key = E.get("UPTIME_KUMA_API_KEY", "").strip()
    if not base or not key or key.startswith("<"):
        return {"state": "degraded", "note": "Uptime Kuma key not set",
                "up": 0, "total": 0, "down": [], "other": [], "certs": []}
    # cert data from /metrics
    cert_days, cert_valid = {}, {}
    try:
        auth = {"Authorization": "Basic " + b64(f":{key}")}
        text = req(f"{base}/metrics", auth)
        for line in text.splitlines():
            if not line or line[0] == "#":
                continue
            m = re.search(r'monitor_name="([^"]*)"', line)
            if not m:
                continue
            name = m.group(1)
            try:
                val = float(line.rsplit("}", 1)[1])
            except (ValueError, IndexError):
                continue
            if line.startswith("monitor_cert_days_remaining{"):
                cert_days[name] = val
            elif line.startswith("monitor_cert_is_valid{"):
                cert_valid[name] = val
    except Exception:
        pass
    for k, days in cert_days.items():
        valid = cert_valid.get(k, 1) == 1
        d["certs"].append({"name": k, "days": int(days), "valid": valid})
    d["certs"].sort(key=lambda x: x["days"])
    # status via SQLite through Portainer exec
    try:
        pbase = E.get("PORTAINER_URL", "").strip().rstrip("/")
        puser = E.get("PORTAINER_USERNAME", "").strip()
        ppw = E.get("PORTAINER_PASSWORD", "").strip()
        if not (pbase and puser and ppw and not ppw.startswith("<")):
            raise ValueError("Portainer creds missing")
        jwt = jget(f"{pbase}/api/auth", data={"Username": puser, "Password": ppw}, method="POST")["jwt"]
        ph = {"Authorization": f"Bearer {jwt}"}
        cid = None
        epid_used = None
        for ep in jget(f"{pbase}/api/endpoints", ph):
            epid = ep.get("Id")
            cs = jget(f"{pbase}/api/endpoints/{epid}/docker/containers/json?all=1", ph)
            cid = next((c.get("Id") for c in cs
                        if "uptime-kuma" in "/".join(c.get("Names") or []).lower()
                        or "uptime-kuma" in str(c.get("Image", "")).lower()), None)
            if cid:
                epid_used = epid
                break
        if not cid:
            raise RuntimeError("uptime-kuma container not found")

        def _kuma_exec(cmd_list):
            ex = jget(f"{pbase}/api/endpoints/{epid_used}/docker/containers/{urllib.parse.quote(cid)}/exec",
                      ph, {"AttachStdout": True, "AttachStderr": True, "Tty": True, "Cmd": cmd_list}, "POST")
            raw = req(f"{pbase}/api/endpoints/{epid_used}/docker/exec/{urllib.parse.quote(ex['Id'])}/start",
                      ph, {"Detach": False, "Tty": True}, "POST")
            return re.sub(r"[^\x20-\x7e\n|]", "", raw if isinstance(raw, str) else raw.decode("utf-8", "replace")).strip()

        monitors_raw = _kuma_exec(["sqlite3", "-separator", "|", "/app/data/kuma.db",
                                    "SELECT id,name FROM monitor WHERE active=1 ORDER BY name;"])
        monitors = []
        for line in monitors_raw.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 2:
                try:
                    monitors.append((int(parts[0]), parts[1]))
                except (ValueError, IndexError):
                    pass
        if not monitors:
            raise RuntimeError("no active monitors found")
        SMAP = {"0": "DOWN", "1": "UP", "2": "PENDING", "3": "MAINT"}
        status = {}
        for mid, name in monitors:
            q = f"SELECT status FROM heartbeat WHERE monitor_id={mid} ORDER BY id DESC LIMIT 1;"
            out = _kuma_exec(["sqlite3", "/app/data/kuma.db", q]).strip()
            if out and "error" not in out.lower() and "malformed" not in out.lower():
                status[name] = SMAP.get(out, f"?{out}")
            else:
                status[name] = "unknown"
        d["total"] = len(monitors)
        d["up"] = sum(1 for v in status.values() if v == "UP")
        d["down"] = sorted(k for k, v in status.items() if v == "DOWN")
        other_raw = [[k, v] for k, v in status.items() if v not in ("UP", "DOWN", "unknown")]
        d["other"] = sorted(other_raw)
        d["status_map"] = {k: (1 if v == "UP" else 0 if v == "DOWN" else 2) for k, v in status.items()}
        unknown = [k for k, v in status.items() if v == "unknown"]
        if unknown:
            d["note"] = f"{len(unknown)} monitor(s) unreadable"
        if d["down"]:
            d["state"] = "crit"
        elif d["other"] or unknown:
            d["state"] = "warn"
    except Exception as e:
        d["state"] = "degraded"
        d["note"] = f"Kuma unavailable: {type(e).__name__}: {e}"
    return d
