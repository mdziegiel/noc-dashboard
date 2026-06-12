#!/usr/bin/env python3
"""
MRDTech Homelab NOC Dashboard generator.
Collects all infra sources (stdlib only, per-source isolation) and renders a
single self-contained static HTML file (inline CSS + SVG, no external assets).
Run every 15 min via cron; served by a tiny http.server systemd unit on :8080.

Reuses the exact API patterns proven in morning_briefing.py and the report_*.py
cron scripts. One failed source never kills the page - it renders a degraded card.
"""
import base64, html, json, os, re, sqlite3, ssl, sys, time
import urllib.request, urllib.parse, http.cookiejar
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ENV_PATH = os.environ.get("HERMES_ENV", os.path.expanduser("~/.hermes/.env"))
OUT_DIR = os.environ.get("NOC_OUT_DIR", os.path.expanduser("~/mrdtech-dashboard"))
OUT_FILE = os.environ.get("NOC_OUT_FILE", os.path.join(OUT_DIR, "index.html"))
TIMEOUT = 15
CERT_WARN_DAYS = 30
DEFAULT_DASHBOARD_TITLE = "NOC Dashboard"
DEFAULT_DASHBOARD_SUBTITLE = "Infrastructure Monitoring"
STATE_DIR = os.environ.get("NOC_STATE_DIR", os.path.join(OUT_DIR, "state"))
CONFIG_FILE = os.environ.get("NOC_CONFIG_FILE", os.path.join(STATE_DIR, "config.json"))
HEALTH_DB_FILE = os.environ.get("NOC_HEALTH_DB", os.path.join(STATE_DIR, "health_history.sqlite3"))
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def load_dashboard_config():
    cfg = {
        "dashboard_title": DEFAULT_DASHBOARD_TITLE,
        "dashboard_subtitle": DEFAULT_DASHBOARD_SUBTITLE,
        "logo_url": "",
        "timezone": "UTC",
        "show_ticker_bar": True,
        "date_format": "YYYY-MM-DD",
        "clock_format": "24hr",
    }
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for key in cfg:
                val = raw.get(key)
                if key == "show_ticker_bar":
                    if isinstance(val, bool):
                        cfg[key] = val
                elif isinstance(val, str):
                    cfg[key] = val.strip()
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"warn: dashboard config load failed: {type(e).__name__}: {str(e)[:80]}")
    cfg["dashboard_title"] = cfg["dashboard_title"] or DEFAULT_DASHBOARD_TITLE
    cfg["dashboard_subtitle"] = cfg["dashboard_subtitle"] or DEFAULT_DASHBOARD_SUBTITLE
    cfg["timezone"] = cfg.get("timezone") or "UTC"
    if not isinstance(cfg.get("show_ticker_bar"), bool):
        cfg["show_ticker_bar"] = True
    if cfg.get("date_format") not in ("MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"):
        cfg["date_format"] = "YYYY-MM-DD"
    if cfg.get("clock_format") not in ("12hr", "24hr"):
        cfg["clock_format"] = "24hr"
    return cfg

def dashboard_logo_html(cfg):
    logo = (cfg.get("logo_url") or "").strip()
    if not logo:
        return ""
    return f'<img class="brand-logo" src="{esc(logo)}" alt="Dashboard logo">'

def load_env(path):
    d = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            # Accept normal .env syntax plus the variants humans inevitably
            # paste in: leading whitespace, optional "export", and spaces
            # around '='. Last-wins for duplicate blocks / stale placeholders.
            m = re.match(r'^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)$', line.rstrip("\n"))
            if m:
                d[m.group(1)] = m.group(2)
    # Cron runs do not inherit Hermes' process environment, but manual runs can.
    # Let real process env override file values without ever printing secrets.
    d.update({k: v for k, v in os.environ.items() if k.startswith(("LIMACHARLIE_", "LIMA_CHARLIE_", "LC_"))})
    return d


E = load_env(ENV_PATH)


def _env_first(*keys):
    """Return the first non-placeholder value from supported .env aliases."""
    for key in keys:
        val = E.get(key, "")
        if val is None:
            continue
        val = str(val).strip().strip('"').strip("'")
        if val and not val.startswith("<"):
            return val
    return ""

def _service_base_url(host_or_url, scheme="https", port=None):
    """Normalize .env host fields that may be bare hosts or full URLs."""
    raw = str(host_or_url or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if port is not None and ":" not in raw:
        raw = f"{raw}:{port}"
    return f"{scheme}://{raw}"


def _b64(s):
    return base64.b64encode(s.encode()).decode()


def req(url, headers=None, data=None, method=None, cookiejar=None):
    h = dict(headers or {})
    if isinstance(data, dict):
        data = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        data = data.encode()
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    if cookiejar is not None:
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=CTX),
            urllib.request.HTTPCookieProcessor(cookiejar))
        resp = opener.open(r, timeout=TIMEOUT)
    else:
        resp = urllib.request.urlopen(r, timeout=TIMEOUT, context=CTX)
    return resp.read().decode("utf-8", "replace")


def jget(url, headers=None, data=None, method=None, cookiejar=None):
    return json.loads(req(url, headers, data, method, cookiejar))


def collect_system_tools_suite():
    base = E.get("SYSTEM_TOOLS_URL", "http://10.10.10.237:10233").strip().rstrip("/")
    d = {"state": "error", "status": "unknown", "app": "System Tools Suite",
         "version": "?", "tool_count": 23, "url": base}
    if not base:
        d.update({"state": "degraded", "note": "SYSTEM_TOOLS_URL not set"})
        return d
    try:
        health = jget(f"{base}/api/health")
        status = str(health.get("status", "unknown")).lower()
        d["status"] = status
        d["app"] = health.get("app") or d["app"]
        if isinstance(health.get("tool_count"), int):
            d["tool_count"] = health["tool_count"]
        elif isinstance(health.get("tools"), list):
            d["tool_count"] = len(health["tools"])
        d["state"] = "ok" if status == "ok" else "warn"
        d["note"] = health.get("note") or "health endpoint responding"
        try:
            info = jget(f"{base}/openapi.json").get("info", {})
            d["version"] = str(info.get("version") or d["version"])
        except Exception:
            pass
        return d
    except Exception as e:
        d["error"] = str(e)[:160]
        return d


def _docker_mux_decode(buf):
    """Decode Docker exec multiplexed stdout/stderr frames."""
    if isinstance(buf, str):
        buf = buf.encode()
    out = bytearray()
    i = 0
    while i + 8 <= len(buf) and buf[i] in (0, 1, 2):
        size = int.from_bytes(buf[i+4:i+8], "big")
        out.extend(buf[i+8:i+8+size])
        i += 8 + size
    if not out:
        out.extend(buf)
    return out.decode("utf-8", "replace")


def _pmox_auth():
    tid = E.get("PROXMOX_TOKEN_ID", "")
    if "!" not in tid and "@pam" in tid:
        tid = tid.replace("@pam", "@pam!")
    sec = E.get("PROXMOX_TOKEN_SECRET", "")
    return {"Authorization": f"PVEAPIToken={tid}={sec}"}


# ============================ COLLECTORS ============================
# Each returns a dict. 'state' in {ok, warn, crit, degraded, error} drives color.

def collect_proxmox():
    d = {"state": "ok", "vms_running": 0, "vms_total": 0, "cpu": 0.0,
         "mem_used": 0.0, "mem_total": 0.0, "node": "?", "uptime_d": 0,
         "down_vms": [], "storage": []}
    auth = _pmox_auth()
    base = _service_base_url(E.get("PROXMOX_HOST", "10.10.10.251"), "https", 8006) + "/api2/json"
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
        vms = [v for v in vms if str(v.get("template", 0)) not in ("1", "true", "True")]
        run = [v for v in vms if v.get("status") == "running"]
        d["vms_running"] = len(run)
        d["vms_total"] = len(vms)
        d["down_vms"] = sorted(
            f"{v['vmid']} {v.get('name','')}".strip()
            for v in vms if v.get("status") != "running")
        if d["down_vms"]:
            d["state"] = "warn"
        elif d["vms_total"] >= 0 and d["vms_running"] == d["vms_total"]:
            d["state"] = "ok"
    else:
        d["state"] = "degraded"
        d["note"] = "token has no ACL grant (0 VMs visible)"
    # storage
    st = jget(f"{base}/nodes/{node}/storage", auth)["data"]
    for s in st:
        if not s.get("total"):
            continue
        used, tot = s.get("used", 0), s.get("total", 1)
        pct = round(100 * used / tot, 1)
        d["storage"].append({"name": s["storage"], "pct": pct,
                             "used_g": round(used / 1e9, 1),
                             "total_g": round(tot / 1e9, 1)})
    d["storage"].sort(key=lambda x: -x["pct"])
    if any(s["pct"] > 85 for s in d["storage"]):
        d["state"] = "crit" if d["state"] != "degraded" else d["state"]
    return d


def _smart_raw_int(v):
    m = re.search(r"-?\d+", str(v or ""))
    return int(m.group(0)) if m else 0


def _smart_short_model(disk):
    return (disk.get("model") or disk.get("serial") or disk.get("devpath") or "disk")[:26]


def collect_smart_health():
    """Read-only SMART/disk health via Proxmox API.

    Proxmox exposes host physical disk SMART. VM disks are virtual block devices;
    guest SMART is not exposed through Proxmox for those, so the tile states that
    explicitly instead of hallucinating green health inside every VM.
    """
    d = {"state": "ok", "checked": 0, "passed": 0, "warn": 0, "fail": 0,
         "prefail": 0, "problems": [], "disks": [], "vm_disks": 0, "vm_note": ""}
    auth = _pmox_auth()
    base = _service_base_url(E.get("PROXMOX_HOST", "10.10.10.251"), "https", 8006) + "/api2/json"
    nodes = jget(f"{base}/nodes", auth).get("data", [])
    if not nodes:
        return {"state": "degraded", "note": "no Proxmox nodes visible", "checked": 0,
                "passed": 0, "warn": 0, "fail": 0, "prefail": 0, "problems": [], "disks": []}

    critical_names = ("realloc", "pending", "uncorrect", "offline_uncorrect", "reported_uncorrect",
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
            rec = {"node": node, "dev": dev, "model": _smart_short_model(disk),
                   "health": disk.get("health") or "UNKNOWN", "wearout": disk.get("wearout"),
                   "issues": []}
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
                attrs = sm.get("attributes", []) or []
                for a in attrs:
                    name = str(a.get("name", ""))
                    fail = str(a.get("fail", "-")).strip()
                    flags = str(a.get("flags", ""))
                    raw = _smart_raw_int(a.get("raw"))
                    is_prefail = flags.startswith("P") or flags.startswith("PO")
                    if is_prefail:
                        d["prefail"] += 1
                    lname = name.lower()
                    if fail and fail != "-":
                        rec["issues"].append(f"{name} {fail}")
                    elif raw > 0 and any(x in lname for x in critical_names):
                        rec["issues"].append(f"{name} raw={raw}")
                # NVMe text-only SMART checks.
                m = re.search(r"Critical Warning:\s*(0x[0-9a-fA-F]+|\d+)", txt)
                if m and int(m.group(1), 0) != 0:
                    rec["issues"].append(f"NVMe critical warning {m.group(1)}")
                m = re.search(r"Media and Data Integrity Errors:\s*([\d,]+)", txt)
                if m and int(m.group(1).replace(",", "")) > 0:
                    rec["issues"].append(f"NVMe media errors {m.group(1)}")
                m = re.search(r"Temperature:\s*(\d+)\s+Celsius", txt)
                if m and int(m.group(1)) >= 70:
                    rec["issues"].append(f"temperature {m.group(1)}C")
            except Exception as e:
                d["warn"] += 1
                rec["issues"].append(f"SMART detail unavailable: {type(e).__name__}")
            if rec["issues"]:
                d["problems"].append(f"{rec['model']} {dev}: " + "; ".join(rec["issues"][:3]))
            d["disks"].append(rec)
    if not d["checked"]:
        d["state"] = "degraded"
        d["note"] = "no SMART-capable disks returned by Proxmox"
    elif d["fail"] or any("raw=" in p or "critical" in p.lower() for p in d["problems"]):
        d["state"] = "crit"
    elif d["warn"] or d["problems"]:
        d["state"] = "warn"
    elif d["passed"] == d["checked"] and not d["problems"]:
        # VM disks are virtual and their guest SMART is unobservable from
        # Proxmox. That is informational; it must not turn a clean host disk
        # result into a grey/degraded card.
        d["state"] = "ok"
    if d["vm_disks"]:
        d["vm_note"] = f'{d["vm_disks"]} VM virtual disk(s); guest SMART not exposed by Proxmox'
    return d


def collect_hyperv():
    """Hyper-V host via WinRM/NTLM. VM list + host resource summary."""
    host = E.get("HYPERV_HOST", "").strip()
    user = E.get("HYPERV_USERNAME", "").strip()
    pwd  = E.get("HYPERV_PASSWORD", "").strip()
    base = {"vms": [], "vm_count": 0, "running": 0, "stopped": 0,
            "host_cpus": "?", "host_mem_gb": "?"}
    if not host or not user or not pwd or pwd.startswith("<"):
        return {**base, "state": "degraded", "note": "Hyper-V creds not configured"}
    try:
        import winrm
    except ImportError:
        return {**base, "state": "error", "note": "pywinrm not installed"}
    try:
        sess = winrm.Session(host, auth=(user, pwd), transport="ntlm",
                             server_cert_validation="ignore",
                             operation_timeout_sec=20, read_timeout_sec=25)
        ps_vms = (
            "try { $vms = Get-VM | Select-Object Name, State, CPUUsage, "
            "@{N='MemGB';E={[math]::Round($_.MemoryAssigned/1GB,2)}}; "
            "if ($vms -eq $null) { Write-Output '[]' } "
            "else { ConvertTo-Json -InputObject @($vms) -Depth 3 } "
            "} catch { Write-Output '[]' }"
        )
        r_vms = sess.run_ps(ps_vms)
        if r_vms.status_code != 0:
            err = (r_vms.std_err or b"").decode("utf-8", "replace")[:180].strip()
            return {**base, "state": "error", "note": f"WinRM error: {err or 'unknown'}"}
        raw = (r_vms.std_out or b"").decode("utf-8", "replace").strip()
        try:
            import json as _j
            vms_raw = _j.loads(raw) if raw else []
        except Exception:
            vms_raw = []
        if isinstance(vms_raw, dict):
            vms_raw = [vms_raw]
        ps_host = (
            "try { $h = Get-VMHost | Select-Object LogicalProcessorCount,"
            "@{N='MemGB';E={[math]::Round($_.MemoryCapacity/1GB,0)}}; "
            "ConvertTo-Json -InputObject $h } catch { Write-Output '{}' }"
        )
        r_host = sess.run_ps(ps_host)
        host_raw = (r_host.std_out or b"").decode("utf-8", "replace").strip()
        try:
            import json as _j
            host_info = _j.loads(host_raw) if host_raw else {}
        except Exception:
            host_info = {}
        if isinstance(host_info, list):
            host_info = host_info[0] if host_info else {}
        vms, running, stopped = [], 0, 0
        for vm in vms_raw:
            if not isinstance(vm, dict):
                continue
            sr = str(vm.get("State", "")).strip()
            if sr in ("2", "Running"):
                vs, running = "Running", running + 1
            elif sr in ("3", "Off"):
                vs, stopped = "Off", stopped + 1
            else:
                vs, stopped = sr or "Unknown", stopped + 1
            vms.append({"name": str(vm.get("Name", "?")), "state": vs,
                        "cpu": float(vm.get("CPUUsage", 0) or 0),
                        "mem_gb": float(vm.get("MemGB", 0) or 0)})
        state = "error" if (not vms and not host_info) else ("warn" if stopped > 0 else "ok")
        return {"state": state, "vm_count": len(vms), "running": running,
                "stopped": stopped, "vms": vms,
                "host_cpus": host_info.get("LogicalProcessorCount", "?"),
                "host_mem_gb": host_info.get("MemGB", "?")}
    except Exception as e:
        return {**base, "state": "error", "note": f"{type(e).__name__}: {str(e)[:140]}"}


def collect_docker():
    d = {"state": "ok", "running": 0, "total": 0, "envs": 0, "bad": []}
    base = E.get("PORTAINER_URL", "").strip().rstrip("/")
    user = E.get("PORTAINER_USERNAME", "").strip()
    pw = E.get("PORTAINER_PASSWORD", "").strip()
    if not base or not user or not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "Portainer creds not set", "running": 0, "total": 0}
    jwt = jget(f"{base}/api/auth", data={"Username": user, "Password": pw}, method="POST")["jwt"]
    auth = {"Authorization": f"Bearer {jwt}"}
    endpoints = jget(f"{base}/api/endpoints", auth)
    d["envs"] = len(endpoints)
    for ep in endpoints:
        epid = ep.get("Id")
        try:
            cs = jget(f"{base}/api/endpoints/{epid}/docker/containers/json?all=1", auth)
        except Exception as e:
            d["bad"].append(f"{ep.get('Name', epid)} unreachable: {type(e).__name__}")
            continue
        run = [c for c in cs if c.get("State") == "running"]
        d["running"] += len(run)
        d["total"] += len(cs)
        for c in cs:
            nm = c.get("Names", ["?"])[0].lstrip("/")
            if "unhealthy" in c.get("Status", "").lower():
                d["bad"].append(f"UNHEALTHY {nm}")
            elif c.get("State") != "running":
                d["bad"].append(f"down {nm}")
    if d["bad"]:
        d["state"] = "warn"
    return d


def collect_pbs():
    d = {"state": "ok", "ok": 0, "fail": 0, "run": 0, "last_backup": "?", "datastores": []}
    tk = jget("https://10.10.10.77:8007/api2/json/access/ticket",
              data=urllib.parse.urlencode({
                  "username": E.get("PBS_USERNAME", "root@pam"),
                  "password": E.get("PBS_PASSWORD", "")}),
              headers={"Content-Type": "application/x-www-form-urlencoded"},
              method="POST")["data"]["ticket"]
    cookie = {"Cookie": f"PBSAuthCookie={urllib.parse.quote(tk, safe='')}"}
    since = int(time.time()) - 86400
    tasks = jget(f"https://10.10.10.77:8007/api2/json/nodes/localhost/tasks"
                 f"?since={since}&limit=500", cookie)["data"]
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
        d["last_backup"] = (f"{ago_h:.1f}h ago" if ago_h < 48
                            else f"{ago_h/24:.1f}d ago")
        if ago_h > 26:
            d["state"] = "warn"
    else:
        d["last_backup"] = "none in 24h"
        d["state"] = "warn"
    if d["fail"]:
        d["state"] = "crit"
    # datastore usage
    try:
        dss = jget("https://10.10.10.77:8007/api2/json/status/datastore-usage", cookie)["data"]
        for ds in dss:
            tot = ds.get("total", 0) or 0
            used = ds.get("used", 0) or 0
            pct = round(100 * used / tot, 1) if tot else 0
            d["datastores"].append({"name": ds.get("store", "?"), "pct": pct})
    except Exception:
        pass
    return d


def collect_uptime_kuma():
    """Uptime Kuma monitor status via per-monitor SQLite queries through Portainer exec.

    Kuma 1.23 does not emit monitor_status in /metrics when the heartbeat b-tree
    index is partially corrupted.  We collect cert data from /metrics (which still
    works) and get actual UP/DOWN status by querying the heartbeat table one
    monitor at a time (bypassing the corrupted composite index).
    """
    d = {"state": "ok", "up": 0, "total": 0, "down": [], "other": [], "certs": []}
    base = E.get("UPTIME_KUMA_URL", "").strip().rstrip("/")
    key = E.get("UPTIME_KUMA_API_KEY", "").strip()
    if not base or not key or key.startswith("<"):
        return {"state": "degraded", "note": "Uptime Kuma key not set", "up": 0, "total": 0,
                "down": [], "other": [], "certs": []}

    # --- Cert data from /metrics (still works even with corrupted heartbeat index) ---
    cert_days, cert_valid = {}, {}
    try:
        auth = {"Authorization": "Basic " + _b64(f":{key}")}
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
        pass  # cert data is optional; status comes from SQLite below

    for k, days in cert_days.items():
        valid = cert_valid.get(k, 1) == 1
        d["certs"].append({"name": k, "days": int(days), "valid": valid})
    d["certs"].sort(key=lambda x: x["days"])

    # --- Actual UP/DOWN status via per-monitor SQLite heartbeat queries ---
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
            raise RuntimeError("uptime-kuma container not found via Portainer")

        def _kuma_exec(cmd_list):
            ex = jget(f"{pbase}/api/endpoints/{epid_used}/docker/containers/{urllib.parse.quote(cid)}/exec",
                      ph, {"AttachStdout": True, "AttachStderr": True, "Tty": True, "Cmd": cmd_list}, "POST")
            raw = req(f"{pbase}/api/endpoints/{epid_used}/docker/exec/{urllib.parse.quote(ex['Id'])}/start",
                      ph, {"Detach": False, "Tty": True}, "POST")
            return re.sub(r"[^\x20-\x7e\n|]", "", raw if isinstance(raw, str) else raw.decode("utf-8", "replace")).strip()

        # Get all active monitors (monitor table is intact)
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
            raise RuntimeError("no active monitors found in Kuma DB")

        # Per-monitor heartbeat query — avoids corrupted composite index
        SMAP_INT = {"0": "DOWN", "1": "UP", "2": "PENDING", "3": "MAINT"}
        status = {}  # name -> "UP"/"DOWN"/"PENDING"/"MAINT"/"unknown"
        for mid, name in monitors:
            q = f"SELECT status FROM heartbeat WHERE monitor_id={mid} ORDER BY id DESC LIMIT 1;"
            out = _kuma_exec(["sqlite3", "/app/data/kuma.db", q]).strip()
            if out and "error" not in out.lower() and "malformed" not in out.lower():
                status[name] = SMAP_INT.get(out, f"?{out}")
            else:
                status[name] = "unknown"

        d["total"] = len(monitors)
        d["up"] = sum(1 for v in status.values() if v == "UP")
        d["down"] = sorted(k for k, v in status.items() if v == "DOWN")
        other_raw = [[k, v] for k, v in status.items() if v not in ("UP", "DOWN", "unknown")]
        unknown = [k for k, v in status.items() if v == "unknown"]
        d["other"] = sorted(other_raw)
        d["status_map"] = {k: (1 if v == "UP" else 0 if v == "DOWN" else 2) for k, v in status.items()}
        d["source"] = "sqlite"
        if unknown:
            d["note"] = f"{len(unknown)} monitor(s) status unreadable (DB corruption): {', '.join(unknown[:4])}"
        if d["down"]:
            d["state"] = "crit"
        elif d["other"] or unknown:
            d["state"] = "warn"

    except Exception as e:
        d["state"] = "degraded"
        d["note"] = f"Kuma status unavailable: {type(e).__name__}: {e}"

    return d


def collect_crowdsec():
    d = {"state": "ok", "bans": 0, "local_bans": 0, "detections_24h": None, "top": []}
    apikey = E.get("CROWDSEC_API_KEY", "")
    dec = jget("http://10.10.10.237:18080/v1/decisions", {"X-Api-Key": apikey})
    if isinstance(dec, list):
        d["bans"] = len(dec)
        local = [x for x in dec if x.get("origin") not in ("lists", "CAPI")]
        d["local_bans"] = len(local)
        scen = Counter(x.get("scenario", "?").split("/")[-1] for x in local)
        d["top"] = [[k, v] for k, v in scen.most_common(3) if k != "?"]
    # local detections 24h via watcher (creds usually empty -> stays None)
    mu = E.get("CROWDSEC_MACHINE_USER", "")
    mp = E.get("CROWDSEC_MACHINE_PASS", "")
    if mu and mp:
        try:
            tok = jget("http://10.10.10.237:18080/v1/watchers/login",
                       {"Content-Type": "application/json"},
                       json.dumps({"machine_id": mu, "password": mp}).encode(), "POST")["token"]
            alerts = jget("http://10.10.10.237:18080/v1/alerts?since=24h&limit=500",
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


def collect_wazuh():
    d = {"state": "ok", "active": 0, "total": 0, "down": []}
    jwt = req("https://10.10.10.233:55000/security/user/authenticate?raw=true",
              {"Authorization": "Basic " + _b64(
                  f"{E.get('WAZUH_API_USER','hermes')}:{E.get('WAZUH_API_PASSWORD','')}")}).strip()
    ag = jget("https://10.10.10.233:55000/agents?limit=500",
              {"Authorization": f"Bearer {jwt}"})["data"]["affected_items"]
    d["total"] = len(ag)
    d["active"] = sum(1 for a in ag if a.get("status") == "active")
    d["down"] = [f"{a.get('id')} {a.get('name','')}".strip()
                 for a in ag if a.get("status") != "active"]
    if d["down"]:
        d["state"] = "warn"
    # alert volume from the indexer (last 24h). Manager API has no per-alert
    # severity; that lives only in wazuh-alerts-*. Degrade silently if missing.
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
                       {"Authorization": "Basic " + _b64(f"{iu}:{ip}")}, data=q,
                       method="POST")
            tot = res.get("hits", {}).get("total", {})
            d["alerts_24h"] = tot.get("value", tot) if isinstance(tot, dict) else tot
            d["high_24h"] = res.get("aggregations", {}).get("hi", {}).get("doc_count", 0)
            if d["high_24h"]:
                d["state"] = "crit"
        except Exception as e:
            d["alerts_err"] = f"{type(e).__name__}"
    return d


def collect_malware_sources():
    """Detection-source tiles (read-only) from the Wazuh indexer, last 24h.

    Liveness is EXPLICIT, never inferred from alert counts (zero alerts must not
    masquerade as "installed and clean" on a security tile). Each source carries
    {live: bool, count: int|None}:
      - not live  -> render "—" (pending install/enrollment)
      - live, 0   -> render "0" (installed, no detections in 24h)
      - live, >0  -> render the count in warn (active detections)

    Flip MALWARE_SOURCE_LIVE[<src>] = True as each source is actually installed
    and confirmed emitting (ClamAV/YARA Tasks 1-2; Defender = Windows task)."""
    # ---- explicit per-source liveness registry (data layer, not count-derived) ----
    MALWARE_SOURCE_LIVE = {
        "clamav": True,       # live on 233 + 251 (EICAR -> rule 52502 confirmed 2026-06-09)
        "yara": True,         # live on 233 + 251 (EICAR -> rule 108001 confirmed 2026-06-09)
        "virustotal": True,   # already integrated and flowing
        "defender": False,    # -> True after Defender->Wazuh enrollment (Windows task)
    }
    SRC_QUERY = {
        # Built-in 0320 ClamAV rules use groups clamd/freshclam/virus (NOT "clamav").
        # Match the clamd group (covers detections rule 52502/52511 + daemon events).
        "clamav": {"term": {"rule.groups": "clamd"}},
        "yara": {"term": {"rule.groups": "yara"}},
        "virustotal": {"term": {"rule.groups": "virustotal"}},
        "defender": {"match_phrase": {
            "data.win.system.providerName": "Microsoft-Windows-Windows Defender"}},
    }
    d = {"state": "ok",
         "sources": {k: {"live": v, "count": None}
                     for k, v in MALWARE_SOURCE_LIVE.items()}}
    iu = E.get("WAZUH_INDEXER_USER", "").strip()
    ip = E.get("WAZUH_INDEXER_PASS", "").strip()
    if not (iu and ip):
        d["state"] = "degraded"
        d["note"] = "indexer creds not set"
        return d
    ix = E.get("WAZUH_INDEXER_HOST", "https://10.10.10.233:9200").rstrip("/")
    auth = {"Authorization": "Basic " + _b64(f"{iu}:{ip}")}

    def cnt(extra):
        q = {"size": 0, "query": {"bool": {"filter": [
            {"range": {"@timestamp": {"gte": "now-24h"}}}, extra]}}}
        res = jget(f"{ix}/wazuh-alerts-*/_search", auth, data=q, method="POST")
        tot = res.get("hits", {}).get("total", {})
        return tot.get("value", tot) if isinstance(tot, dict) else tot

    # only query the 24h count for sources explicitly marked live
    for key, live in MALWARE_SOURCE_LIVE.items():
        if not live:
            continue
        try:
            d["sources"][key]["count"] = cnt(SRC_QUERY[key])
        except Exception as e:
            d["sources"][key]["err"] = type(e).__name__
    # active detections on any live source escalate the card to warn
    hits = sum(s["count"] for s in d["sources"].values()
               if s["live"] and isinstance(s["count"], int))
    if hits:
        d["state"] = "warn"
    return d


def collect_unifi():
    d = {"state": "ok", "wan": "?", "wan_ip": "?", "clients": 0, "ips_24h": 0,
         "latency": None, "down_mbps": None, "up_mbps": None, "devices": [],
         "ssids": [], "month_rx": None, "month_tx": None, "month_total": None,
         "pia": None}
    GW = "https://10.10.10.1"
    NET = GW + "/proxy/network/api/s/default"
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPCookieProcessor(cj))
    op.open(urllib.request.Request(
        f"{GW}/api/auth/login",
        data=json.dumps({"username": E.get("UNIFI_USERNAME", ""),
                         "password": E.get("UNIFI_PASSWORD", "")}).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=TIMEOUT)
    csrf = None
    tok = next((c.value for c in cj if c.name == "TOKEN"), None)
    if tok:
        try:
            p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
            csrf = json.loads(base64.urlsafe_b64decode(p)).get("csrfToken")
        except Exception:
            pass
    hdr = {"Content-Type": "application/json"}
    if csrf:
        hdr["X-CSRF-Token"] = csrf

    def call(path, data=None, method="GET"):
        body = json.dumps(data).encode() if data is not None else None
        r = urllib.request.Request(NET + path, data=body, headers=hdr,
                                   method=("POST" if data is not None else method))
        return json.loads(op.open(r, timeout=TIMEOUT).read())

    health = call("/stat/health").get("data", [])
    wan = next((h for h in health if h.get("subsystem") == "wan"), {})
    www = next((h for h in health if h.get("subsystem") == "www"), {})
    d["wan"] = wan.get("status", "?")
    d["wan_ip"] = wan.get("wan_ip", "?")
    d["latency"] = www.get("latency")
    d["down_mbps"] = www.get("xput_down")
    d["up_mbps"] = www.get("xput_up")
    # clients = sum of num_user across lan + wlan subsystems
    clients = 0
    for h in health:
        if h.get("subsystem") in ("lan", "wlan"):
            clients += int(h.get("num_user", 0) or 0)
    d["clients"] = clients
    if d["wan"] != "ok":
        d["state"] = "crit"
    # IPS alarms 24h
    try:
        alarms = call("/list/alarm").get("data", [])
        cutoff = (time.time() - 86400) * 1000
        ips = [a for a in alarms
               if (a.get("time") or a.get("timestamp") or 0) >= cutoff
               and (a.get("key") == "EVT_IPS_IpsAlert" or a.get("inner_alert_signature"))]
        d["ips_24h"] = len(ips)
        if len(ips) > 0 and d["state"] == "ok":
            d["state"] = "warn"
    except Exception:
        d["ips_24h"] = 0
    # Network devices: UDM-SE, switches, APs (name + uptime)
    try:
        devs = call("/stat/device").get("data", [])
        TMAP = {"udm": "Gateway", "ugw": "Gateway", "usw": "Switch",
                "uap": "Access Point", "usg": "Gateway"}

        def fmt_uptime(s):
            s = int(s or 0)
            dd, hh = s // 86400, (s % 86400) // 3600
            if dd:
                return f"{dd}d {hh}h"
            mm = (s % 3600) // 60
            return f"{hh}h {mm}m"
        torder = {"udm": 0, "ugw": 0, "usg": 0, "usw": 1, "uap": 2}
        for dev in sorted(devs, key=lambda x: (torder.get(x.get("type"), 9),
                                               x.get("name", ""))):
            up = int(dev.get("uptime", 0) or 0)
            online = dev.get("state") == 1
            d["devices"].append({
                "name": dev.get("name", dev.get("model", "?")),
                "kind": TMAP.get(dev.get("type"), dev.get("type", "?")),
                "model": dev.get("model", "?"),
                "uptime": fmt_uptime(up) if online else "offline",
                "online": online})
            if not online:
                d["problems"] = d.get("problems", [])
                if d["state"] == "ok":
                    d["state"] = "warn"
    except Exception:
        pass

    # ---- WiFi clients per SSID (from active stations) ----
    try:
        sta = call("/stat/sta").get("data", [])
        ssid_ct = Counter()
        for c in sta:
            e = c.get("essid")
            if e:
                ssid_ct[e] += 1
        # Always surface the three networks Michael tracks, even at 0 clients
        WANTED = ["ZOMBIELAND5G", "ZOMBIELAND2G", "IOTNetwork"]
        seen = set()
        for name in WANTED:
            d["ssids"].append({"name": name, "clients": int(ssid_ct.get(name, 0))})
            seen.add(name)
        for name, ct in ssid_ct.most_common():
            if name not in seen:
                d["ssids"].append({"name": name, "clients": int(ct)})
    except Exception:
        pass

    # ---- Current-month WAN data usage ----
    try:
        rows = call("/stat/report/monthly.site",
                    {"attrs": ["wan-tx_bytes", "wan-rx_bytes", "time"], "n": 2},
                    "POST").get("data", [])
        if rows:
            cur = rows[-1]
            d["month_tx"] = cur.get("wan-tx_bytes")
            d["month_rx"] = cur.get("wan-rx_bytes")
            d["month_total"] = (cur.get("wan-tx_bytes", 0) or 0) + (cur.get("wan-rx_bytes", 0) or 0)
    except Exception:
        pass

    # ---- PIA VPN client status + uptime ----
    try:
        ncs = call("/rest/networkconf").get("data", [])
        pia = next((n for n in ncs
                    if n.get("purpose") == "vpn-client"
                    and "pia" in (n.get("name", "").lower())), None)
        if pia is None:
            pia = next((n for n in ncs if n.get("purpose") == "vpn-client"), None)
        if pia:
            status = pia.get("openvpn_configuration_status", "?")
            enabled = bool(pia.get("enabled"))
            connected = (str(status).upper() == "VALID") and enabled
            # The controller does not expose VPN-client uptime for a vpn-client
            # network (no uptime/up field on the gateway), so we report status only.
            d["pia"] = {"name": pia.get("name", "PIAVPN"), "status": str(status),
                        "enabled": enabled, "connected": connected, "uptime": "n/a"}
            if not connected and d["state"] == "ok":
                d["state"] = "warn"
    except Exception:
        pass
    return d


def collect_adguard():
    d = {"state": "ok", "queries": 0, "blocked": 0, "block_pct": 0.0, "avg_ms": 0.0}
    s = jget("http://10.10.10.21/control/stats",
             {"Authorization": "Basic " + _b64(f"mdziegiel:{E.get('ADGUARD_PASSWORD','')}")})
    tot = s.get("num_dns_queries", 0)
    blk = s.get("num_blocked_filtering", 0)
    d["queries"] = tot
    d["blocked"] = blk
    d["block_pct"] = round(100 * blk / tot, 1) if tot else 0.0
    d["avg_ms"] = round(s.get("avg_processing_time", 0) * 1000, 1)
    return d


def collect_urbackup():
    """URBackup web API (salt/login/status). User is michaeld (URBACKUP_USERNAME)."""
    d = {"state": "ok", "total": 0, "online": 0, "clients": [], "problems": []}
    base = E.get("URBACKUP_URL", "http://10.10.10.76:55414").rstrip("/")
    user = E.get("URBACKUP_USERNAME", "michaeld")
    pw = E.get("URBACKUP_PASSWORD", "")
    if not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "URBACKUP_PASSWORD not set",
                "total": 0, "online": 0, "clients": [], "problems": []}

    def api(action, body=""):
        url = base + "/x?a=" + action
        r = urllib.request.Request(url, data=body.encode(), method="POST",
                                   headers={"Content-Type": "application/json; charset=utf-8"})
        return json.loads(urllib.request.urlopen(r, timeout=TIMEOUT, context=CTX).read().decode("utf-8", "replace"))

    s = api("salt", "username=" + urllib.parse.quote(user))
    if s.get("error") == 1 or not s.get("salt"):
        raise RuntimeError("URBackup user not found")
    salt, rnd = s.get("salt", ""), s.get("rnd", "")
    rounds = int(s.get("pbkdf2_rounds", 0) or 0)
    ses = s.get("ses")
    import hashlib as _h
    pwmd5 = _h.md5((salt + pw).encode()).hexdigest()
    if rounds > 0:
        pwmd5 = _h.pbkdf2_hmac("sha256", bytes.fromhex(pwmd5), salt.encode(), rounds, dklen=32).hex()
    final = _h.md5((rnd + pwmd5).encode()).hexdigest()
    body = "username=" + urllib.parse.quote(user) + "&password=" + final
    if ses:
        body += "&ses=" + ses
    r3 = api("login", body)
    if not r3.get("success"):
        raise RuntimeError("URBackup login failed")
    ses = r3.get("session") or ses
    st = api("status", "ses=" + ses if ses else "")
    clients = st.get("status", [])
    d["total"] = len(clients)
    d["online"] = sum(1 for c in clients if c.get("online"))
    now = time.time()
    for c in sorted(clients, key=lambda x: x.get("name", "")):
        name = c.get("name", "?")
        lf = c.get("lastbackup", 0) or c.get("last_filebackup", 0) or 0
        li = c.get("lastbackup_image", 0) or c.get("last_imagebackup", 0) or c.get("last_image_backup", 0) or 0
        issues = c.get("last_filebackup_issues", 0) or 0
        on = bool(c.get("online"))
        lf_h = (now - lf) / 3600.0 if lf else 1e9
        li_h = (now - li) / 3600.0 if li else 1e9
        ago = ("never" if not lf else
               f"{lf_h*60:.0f}m" if lf_h < 1 else
               f"{lf_h:.1f}h" if lf_h < 48 else f"{lf_h/24:.1f}d")
        img_ago = ("never" if not li else
                   f"{li_h*60:.0f}m" if li_h < 1 else
                   f"{li_h:.1f}h" if li_h < 48 else f"{li_h/24:.1f}d")
        cstate = "ok"
        if lf == 0:
            d["problems"].append(f"{name}: no file backup on record"); cstate = "crit"
        elif lf_h > 26:
            d["problems"].append(f"{name}: last backup {ago} ago (>26h)"); cstate = "warn"
        if issues:
            d["problems"].append(f"{name}: {issues} backup issue(s) last run")
            cstate = "warn" if cstate == "ok" else cstate
        if not on:
            d["problems"].append(f"{name}: client OFFLINE")
            cstate = "warn" if cstate == "ok" else cstate
        d["clients"].append({"name": name, "ago": ago, "online": on,
                             "issues": issues, "state": cstate,
                             "last_file_backup": ago, "last_image_backup": img_ago,
                             "file_recent": bool(lf and lf_h <= 26 and not issues),
                             "image_recent": bool(li and li_h <= 24 * 8),
                             "image_days": (round(li_h / 24, 1) if li else None)})
    if any(c["state"] == "crit" for c in d["clients"]):
        d["state"] = "crit"
    elif d["problems"]:
        d["state"] = "warn"
    return d


def _qnap_text(el):
    return (el.text or "").strip() if el is not None else ""


def collect_qnap_one(ip, label):
    """One QNAP NAS: volumes, disk SMART health, system/cpu temp, fan, uptime."""
    import xml.etree.ElementTree as ET
    d = {"state": "ok", "label": label, "ip": ip, "host": "?", "model": "?",
         "cpu_temp": None, "sys_temp": None, "uptime_d": None, "fan_ok": True,
         "volumes": [], "disks": [], "problems": []}
    user = E.get("QNAP_USERNAME", "admin")
    pw = E.get("QNAP_PASSWORD", "")
    if not ip or not pw:
        return {"state": "degraded", "label": label, "ip": ip or "?",
                "note": "QNAP creds not set", "volumes": [], "disks": [], "problems": []}
    # auth
    aurl = f"https://{ip}/cgi-bin/authLogin.cgi"
    adata = urllib.parse.urlencode({"user": user, "pwd": _b64(pw)}).encode()
    abody = urllib.request.urlopen(urllib.request.Request(aurl, data=adata),
                                   timeout=TIMEOUT, context=CTX).read().decode("utf-8", "replace")
    m = re.search(r"<authSid><!\[CDATA\[(.*?)\]\]></authSid>", abody) or re.search(r"<authSid>(.*?)</authSid>", abody)
    sid = m.group(1) if m else ""
    if not sid:
        raise RuntimeError("QNAP auth failed (no sid)")

    def get(path):
        return urllib.request.urlopen(f"https://{ip}{path}", timeout=TIMEOUT, context=CTX).read().decode("utf-8", "replace")

    # ----- sysinfo: temps, fan, uptime, hostname -----
    si = ET.fromstring(get(f"/cgi-bin/management/manaRequest.cgi?subfunc=sysinfo&sid={sid}"))
    def sif(tag):
        e = si.find(".//" + tag)
        return _qnap_text(e)
    d["host"] = sif("hostname") or "?"
    d["model"] = sif("displayModelName") or "?"
    try:
        d["cpu_temp"] = int(sif("cpu_tempc"))
    except (ValueError, TypeError):
        pass
    try:
        d["sys_temp"] = int(sif("sys_tempc"))
    except (ValueError, TypeError):
        pass
    try:
        d["uptime_d"] = int(sif("uptime_day"))
    except (ValueError, TypeError):
        pass
    # fan: any sysfan*_stat != 0 or sysfan_fail* == 1 => fault
    fan_ok = True
    for k in range(1, 6):
        st = si.find(f".//sysfan{k}_stat")
        fl = si.find(f".//sysfan_fail{k}")
        if st is not None and _qnap_text(st) not in ("0", ""):
            fan_ok = False
        if fl is not None and _qnap_text(fl) == "1":
            fan_ok = False
    d["fan_ok"] = fan_ok
    if not fan_ok:
        d["problems"].append("fan fault")
    # temp thresholds (from device): SysTempWarnT etc.; use sane fallbacks
    try:
        sys_warn = int(sif("SysTempWarnT") or 60)
    except ValueError:
        sys_warn = 60
    if d["sys_temp"] is not None and d["sys_temp"] >= sys_warn:
        d["problems"].append(f"system temp {d['sys_temp']}C >= {sys_warn}C")
        d["state"] = "warn"

    # ----- volume usage -----
    vu = ET.fromstring(get(f"/cgi-bin/management/chartReq.cgi?chart_func=disk_usage&disk_select=all&include=all&sid={sid}"))
    labels = {}
    for vol in vu.findall(".//volumeList/volume"):
        vv = _qnap_text(vol.find("volumeValue"))
        labels[vv] = _qnap_text(vol.find("volumeLabel")) or ("Vol " + vv)
        vstat = _qnap_text(vol.find("volumeStatus"))
        if vstat not in ("0", "", "Ready"):
            d["problems"].append(f"volume {labels[vv]} status={vstat}")
    for vu_el in vu.findall(".//volumeUseList/volumeUse"):
        vv = _qnap_text(vu_el.find("volumeValue"))
        try:
            tot = int(_qnap_text(vu_el.find("total_size")) or 0)
            free = int(_qnap_text(vu_el.find("free_size")) or 0)
        except ValueError:
            continue
        if not tot:
            continue
        used = tot - free
        pct = round(100 * used / tot, 1)
        nm = labels.get(vv, "Vol " + vv)
        d["volumes"].append({"name": nm, "pct": pct,
                             "used_t": round(used / 1e12, 2), "total_t": round(tot / 1e12, 2)})
        if pct > 90:
            d["problems"].append(f"volume {nm} {pct:.0f}% full")
            d["state"] = "crit"
        elif pct > 85 and d["state"] == "ok":
            d["state"] = "warn"
    d["volumes"].sort(key=lambda x: -x["pct"])

    # ----- disk SMART health -----
    dh = ET.fromstring(get(f"/cgi-bin/disk/qsmart.cgi?func=all_hd_data&sid={sid}"))
    for e in dh.findall(".//Disk_Info/entry"):
        alias = _qnap_text(e.find("Disk_Alias"))
        health = _qnap_text(e.find("Health"))
        dstat = _qnap_text(e.find("Disk_Status"))
        tc = _qnap_text(e.find("Temperature/oC"))
        try:
            tc = int(tc)
        except ValueError:
            tc = None
        # Skip empty bays: QTS reports unpopulated slots with Disk_Status == -5,
        # no temperature, and a bare "SATA N" alias (no HDD/SSD designation).
        if dstat == "-5" and tc is None:
            continue
        d["disks"].append({"alias": alias, "health": health or "?",
                          "status": dstat, "temp": tc})
        if health and health.upper() not in ("OK", "GOOD", "NORMAL", ""):
            d["problems"].append(f"disk {alias} health={health}")
            d["state"] = "crit"
        elif dstat not in ("0", "", "Ready", "ready"):
            # Disk_Status 0 = good on QTS; any other non-empty status on a
            # populated disk is worth a warning.
            d["problems"].append(f"disk {alias} status={dstat}")
            if d["state"] != "crit":
                d["state"] = "warn"
    return d


def collect_qnaps():
    """Aggregate wrapper: returns a dict of per-unit results keyed q1/q2/q3."""
    units = [("QNAP1", E.get("QNAP1_HOST")), ("QNAP2", E.get("QNAP2_HOST")),
             ("QNAP3", E.get("QNAP3_HOST"))]
    out = {"state": "ok", "units": []}
    worst = "ok"
    order = ["ok", "degraded", "warn", "crit", "error"]
    for label, ip in units:
        try:
            r = collect_qnap_one(ip, label)
        except Exception as e:
            r = {"state": "error", "label": label, "ip": ip or "?",
                 "error": f"{type(e).__name__}: {str(e)[:100]}",
                 "volumes": [], "disks": [], "problems": []}
        out["units"].append(r)
        if order.index(r.get("state", "error")) > order.index(worst):
            worst = r.get("state", "error")
    out["state"] = worst
    return out


def collect_homeassistant():
    """Home Assistant: entity count + active alerts / unavailable entities."""
    d = {"state": "ok", "entities": 0, "alerts_on": 0, "notifications": 0,
         "unavailable": 0, "alert_names": [], "domains": 0}
    base = E.get("HASS_URL", "").rstrip("/")
    tok = E.get("HASS_TOKEN", "")
    if not base or not tok or tok.startswith("<"):
        return {"state": "degraded", "note": "HASS_URL/HASS_TOKEN not set",
                "entities": 0, "alerts_on": 0, "notifications": 0,
                "unavailable": 0, "alert_names": []}
    states = jget(base + "/api/states", {"Authorization": "Bearer " + tok})
    d["entities"] = len(states)
    d["domains"] = len(set(e["entity_id"].split(".")[0] for e in states))
    on_alerts = [e for e in states if e["entity_id"].startswith("alert.") and e.get("state") == "on"]
    notes = [e for e in states if e["entity_id"].startswith("persistent_notification.")]
    unavail = [e for e in states if e.get("state") in ("unavailable", "unknown")]
    d["alerts_on"] = len(on_alerts)
    d["notifications"] = len(notes)
    d["unavailable"] = len(unavail)
    d["alert_names"] = sorted(
        (e.get("attributes", {}).get("friendly_name") or e["entity_id"]) for e in on_alerts)[:6]
    if on_alerts:
        d["state"] = "crit"
    elif notes:
        d["state"] = "warn"
    return d


# ============================ MEDIA STACK COLLECTORS ============================
UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _arr_base(prefix):
    base = E.get(prefix + "_URL", "").strip().rstrip("/")
    key = E.get(prefix + "_API_KEY", "").strip()
    return base, key


def collect_sonarr():
    base, key = _arr_base("SONARR")
    if not base or not key:
        return {"state": "degraded", "note": "SONARR not configured"}
    h = {"X-Api-Key": key}
    series = jget(f"{base}/api/v3/series", h)
    monitored = sum(1 for s in series if s.get("monitored"))
    queue = jget(f"{base}/api/v3/queue?page=1&pageSize=1", h).get("totalRecords", 0)
    missing = jget(f"{base}/api/v3/wanted/missing?page=1&pageSize=1", h).get("totalRecords", 0)
    state = "warn" if (queue > 0 or missing > 0) else "ok"
    return {"state": state, "total": len(series), "monitored": monitored,
            "queue": queue, "missing": missing}


def collect_radarr():
    base, key = _arr_base("RADARR")
    if not base or not key:
        return {"state": "degraded", "note": "RADARR not configured"}
    h = {"X-Api-Key": key}
    movies = jget(f"{base}/api/v3/movie", h)
    monitored = sum(1 for m in movies if m.get("monitored"))
    queue = jget(f"{base}/api/v3/queue?page=1&pageSize=1", h).get("totalRecords", 0)
    missing = jget(f"{base}/api/v3/wanted/missing?page=1&pageSize=1", h).get("totalRecords", 0)
    state = "warn" if (queue > 0 or missing > 0) else "ok"
    return {"state": state, "total": len(movies), "monitored": monitored,
            "queue": queue, "missing": missing}


def collect_lidarr():
    base, key = _arr_base("LIDARR")
    if not base or not key:
        return {"state": "degraded", "note": "LIDARR not configured"}
    h = {"X-Api-Key": key}
    artists = jget(f"{base}/api/v1/artist", h)
    monitored = sum(1 for a in artists if a.get("monitored"))
    queue = jget(f"{base}/api/v1/queue?page=1&pageSize=1", h).get("totalRecords", 0)
    missing = jget(f"{base}/api/v1/wanted/missing?page=1&pageSize=1", h).get("totalRecords", 0)
    state = "warn" if (queue > 0 or missing > 0) else "ok"
    return {"state": state, "total": len(artists), "monitored": monitored,
            "queue": queue, "missing": missing}


def collect_prowlarr():
    base, key = _arr_base("PROWLARR")
    if not base or not key:
        return {"state": "degraded", "note": "PROWLARR not configured"}
    h = {"X-Api-Key": key}
    idx = jget(f"{base}/api/v1/indexer", h)
    enabled = sum(1 for i in idx if i.get("enable"))
    # indexerstatus lists indexers currently in a failed/back-off state
    try:
        failing = len(jget(f"{base}/api/v1/indexerstatus", h))
    except Exception:
        failing = 0
    healthy = enabled - failing
    state = "warn" if failing else "ok"
    return {"state": state, "total": len(idx), "enabled": enabled,
            "healthy": max(healthy, 0), "failing": failing}


def collect_sabnzbd():
    base = E.get("SABNZBD_URL", "").strip().rstrip("/")
    key = E.get("SABNZBD_API_KEY", "").strip()
    if not base or not key:
        return {"state": "degraded", "note": "SABNZBD not configured"}
    q = jget(f"{base}/api?mode=queue&output=json&apikey={key}").get("queue", {})
    try:
        slots = int(q.get("noofslots", 0))
    except (TypeError, ValueError):
        slots = 0
    try:
        kbps = float(q.get("kbpersec", 0) or 0)
    except (TypeError, ValueError):
        kbps = 0.0
    speed_mbps = round(kbps / 1024, 1)
    status = q.get("status", "Idle")
    mbleft = q.get("mbleft", "0")
    timeleft = q.get("timeleft", "0:00:00")
    # daily total
    day_bytes = 0
    try:
        srv = jget(f"{base}/api?mode=server_stats&output=json&apikey={key}")
        day_bytes = int(srv.get("day", 0) or 0)
    except Exception:
        pass
    day_gb = round(day_bytes / (1024 ** 3), 2)
    state = "warn" if status.lower() in ("paused",) else "ok"
    return {"state": state, "slots": slots, "speed_mbps": speed_mbps,
            "status": status, "mbleft": mbleft, "timeleft": timeleft,
            "day_gb": day_gb}


def collect_seerr():
    base = _env_first("SEERR_URL", "OVERSEERR_URL").rstrip("/")
    key = _env_first("SEERR_API_KEY", "OVERSEERR_API_KEY")
    if not base or not key:
        return {"state": "degraded", "note": "SEERR not configured"}
    h = {"X-Api-Key": key, "User-Agent": UA_BROWSER, "Accept": "application/json"}
    # Primary is the local IP (set in .env). If that fails, fall back to the
    # public domain so a container/IP change still has a chance. The 403 seen
    # historically was a TRUNCATED api key, not auth scheme / Cloudflare.
    candidates = [base]
    dom = "https://overseerr.mrdtech.me"
    if dom != base:
        candidates.append(dom)
    last_err = None
    for url in candidates:
        try:
            c = jget(f"{url}/api/v1/request/count", h)
            pending = c.get("pending", 0)
            state = "warn" if pending else "ok"
            return {"state": state, "pending": pending,
                    "approved": c.get("approved", 0), "available": c.get("available", 0),
                    "processing": c.get("processing", 0), "total": c.get("total", 0)}
        except Exception as e:
            last_err = e
            continue
    raise last_err


def collect_tautulli():
    base = E.get("TAUTULLI_URL", "").strip().rstrip("/")
    key = E.get("TAUTULLI_API_KEY", "").strip()
    if not base or not key:
        return {"state": "degraded", "note": "TAUTULLI not configured"}
    act = jget(f"{base}/api/v2?apikey={key}&cmd=get_activity"
               ).get("response", {}).get("data", {})
    streams = act.get("stream_count", 0)
    try:
        streams = int(streams)
    except (TypeError, ValueError):
        streams = 0
    # plays today
    pbd = jget(f"{base}/api/v2?apikey={key}&cmd=get_plays_by_date&time_range=1"
               ).get("response", {}).get("data", {})
    plays_today = 0
    for s in pbd.get("series", []):
        if s.get("name") == "Total":
            plays_today = sum(int(x or 0) for x in (s.get("data") or []))
    # most active user today
    top_user, top_plays = None, 0
    hs = jget(f"{base}/api/v2?apikey={key}&cmd=get_home_stats&time_range=1&stats_count=5"
              ).get("response", {}).get("data", [])
    for sec in hs:
        if sec.get("stat_id") == "top_users":
            rows = sec.get("rows", [])
            if rows:
                top_user = rows[0].get("friendly_name") or rows[0].get("user")
                top_plays = rows[0].get("total_plays", 0)
            break
    return {"state": "ok", "streams": streams, "plays_today": plays_today,
            "top_user": top_user, "top_plays": top_plays}


def collect_plex():
    base = E.get("PLEX_URL", "").strip().rstrip("/")
    tok = E.get("PLEX_TOKEN", "").strip()
    if not base or not tok:
        return {"state": "degraded", "note": "PLEX not configured"}
    h = {"X-Plex-Token": tok, "Accept": "application/json"}
    sess = jget(f"{base}/status/sessions", h).get("MediaContainer", {})
    streams = sess.get("size", 0)
    try:
        streams = int(streams)
    except (TypeError, ValueError):
        streams = 0
    libs = jget(f"{base}/library/sections", h).get("MediaContainer", {}).get("Directory", [])
    movies = shows = 0
    for d in libs:
        k, t = d.get("key"), d.get("type")
        try:
            mc = jget(f"{base}/library/sections/{k}/all"
                      f"?X-Plex-Container-Start=0&X-Plex-Container-Size=0", h
                      ).get("MediaContainer", {})
            sz = mc.get("totalSize", mc.get("size", 0)) or 0
            sz = int(sz)
        except Exception:
            sz = 0
        if t == "movie":
            movies += sz
        elif t == "show":
            shows += sz
    return {"state": "ok", "streams": streams, "movies": movies, "shows": shows}


def collect_adguard2():
    base = E.get("ADGUARD2_URL", "").strip().rstrip("/")
    user = E.get("ADGUARD2_USERNAME", "").strip()
    pw = E.get("ADGUARD2_PASSWORD", "").strip()
    if not base or not user:
        return {"state": "degraded", "note": "ADGUARD2 not configured"}
    d = {"state": "ok", "queries": 0, "blocked": 0, "block_pct": 0.0, "avg_ms": 0.0}
    s = jget(f"{base}/control/stats",
             {"Authorization": "Basic " + _b64(f"{user}:{pw}")})
    tot = s.get("num_dns_queries", 0)
    blk = s.get("num_blocked_filtering", 0)
    d["queries"] = tot
    d["blocked"] = blk
    d["block_pct"] = round(100 * blk / tot, 1) if tot else 0.0
    d["avg_ms"] = round(s.get("avg_processing_time", 0) * 1000, 1)
    return d


def _human_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def collect_cloudflare():
    """Cloudflare GraphQL Analytics. requests/threats/bandwidth today (1dGroups)
    + WAF events / blocked-IP counts last 24h (firewallEventsAdaptiveGroups).
    The firewall dataset needs the token's Firewall/Analytics scope on the zone;
    if it's not granted the API returns an authz error - we degrade that one
    line to a note rather than failing the whole card."""
    import datetime as _dt
    token = E.get("CLOUDFLARE_TOKEN", "").strip()
    zone = E.get("CLOUDFLARE_ZONE_ID", "").strip()
    if not token or not zone or token.startswith("<"):
        return {"state": "degraded", "note": "Cloudflare token/zone not set",
                "requests": 0, "threats": 0, "bytes": 0, "waf": None}
    d = {"state": "ok", "requests": 0, "threats": 0, "bytes": 0,
         "waf_events": None, "waf_blocked": None, "waf_note": None}
    api = "https://api.cloudflare.com/client/v4/graphql"
    auth = {"Authorization": f"Bearer {token}"}
    today = _dt.date.today().isoformat()
    dt24 = (_dt.datetime.now(_dt.UTC) - _dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # --- HTTP analytics (today) ---
    q1 = ("query($z:String!,$d:String!){viewer{zones(filter:{zoneTag:$z}){"
          "httpRequests1dGroups(limit:1,filter:{date_geq:$d}){"
          "sum{requests bytes threats}}}}}")
    r1 = jget(api, auth, {"query": q1, "variables": {"z": zone, "d": today}}, "POST")
    if r1.get("errors"):
        raise RuntimeError("CF http analytics: " + str(r1["errors"][0].get("message", ""))[:120])
    grp = r1["data"]["viewer"]["zones"][0]["httpRequests1dGroups"]
    if grp:
        s = grp[0]["sum"]
        d["requests"] = s.get("requests", 0)
        d["threats"] = s.get("threats", 0)
        d["bytes"] = s.get("bytes", 0)
    if d["threats"]:
        d["state"] = "warn"
    # --- WAF / firewall events (24h), best-effort ---
    q2 = ("query($z:String!,$d:Time!){viewer{zones(filter:{zoneTag:$z}){"
          "all:firewallEventsAdaptiveGroups(limit:1,filter:{datetime_geq:$d}){count}"
          "blk:firewallEventsAdaptiveGroups(limit:1,filter:{datetime_geq:$d,action:\"block\"}){count}"
          "}}}")
    try:
        r2 = jget(api, auth, {"query": q2, "variables": {"z": zone, "d": dt24}}, "POST")
        if r2.get("errors"):
            msg = str(r2["errors"][0].get("message", ""))
            if "does not have access" in msg or "authz" in msg.lower():
                # HTTP analytics above succeeded with this same token, so the
                # token DOES have Analytics Read. firewallEventsAdaptiveGroups is
                # a Pro+ dataset - on a Free zone it returns this authz error
                # regardless of token scope. Not fixable by re-scoping the token.
                d["waf_note"] = "WAF analytics needs Pro plan (Free zone)"
            else:
                d["waf_note"] = msg[:60]
        else:
            z = r2["data"]["viewer"]["zones"][0]
            d["waf_events"] = (z.get("all") or [{}])[0].get("count", 0)
            d["waf_blocked"] = (z.get("blk") or [{}])[0].get("count", 0)
            if d["waf_blocked"] and d["state"] == "ok":
                d["state"] = "warn"
    except Exception as e:
        d["waf_note"] = f"WAF query failed: {type(e).__name__}"
    return d


def collect_npm():
    """Nginx Proxy Manager. POST /api/tokens -> JWT, then proxy-hosts +
    certificates. Flags hosts that are disabled or report an nginx error."""
    base = E.get("NPM_URL", "").strip().rstrip("/")
    email = E.get("NPM_EMAIL", "").strip()
    pw = E.get("NPM_PASSWORD", "").strip()
    if not base or not email or not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "NPM creds not set",
                "hosts": 0, "enabled": 0, "disabled": 0, "certs": 0, "problems": []}
    d = {"state": "ok", "hosts": 0, "enabled": 0, "disabled": 0,
         "errored": 0, "certs": 0, "certs_expiring": 0, "problems": [],
         "cert_list": []}
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
            err = str(meta.get("nginx_err") or "offline")[:50]
            d["problems"].append(f"ERROR {nm}: {err}")
    # certificates
    try:
        certs = jget(f"{base}/api/nginx/certificates", auth)
        d["certs"] = len(certs)
        now = time.time()
        for c in certs:
            exp = c.get("expires_on")
            if not exp:
                continue
            nm = (c.get("domain_names") or [c.get("nice_name") or "?"])[0]
            prov = c.get("provider") or ""
            try:
                ep = time.mktime(time.strptime(exp[:19], "%Y-%m-%dT%H:%M:%S"))
                days = int((ep - now) / 86400)
                d["cert_list"].append({"name": nm, "days": days, "provider": prov})
                if days <= 14:
                    d["certs_expiring"] += 1
                    d["problems"].append(
                        f"cert expiring: {(c.get('nice_name') or nm)}")
            except Exception:
                pass
        # soonest first; cap absurd custom-cert lifetimes for sane display
        d["cert_list"].sort(key=lambda x: x["days"])
    except Exception:
        pass
    if d["errored"]:
        d["state"] = "crit"
    elif d["disabled"] or d["certs_expiring"]:
        d["state"] = "warn"
    return d


def collect_tailscale():
    """Tailscale tailnet devices via the v2 API. The v2 /devices endpoint does
    NOT return a live `online` boolean, so we derive online from lastSeen
    recency (<5 min = online). Also surfaces exit-node advertisers and the
    soonest non-disabled key expiry."""
    import datetime as _dt
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
    now = _dt.datetime.now(_dt.UTC)
    soonest = None
    for dev in devs:
        ls = dev.get("lastSeen", "")
        online = False
        if ls:
            try:
                t = _dt.datetime.strptime(ls, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.UTC)
                online = (now - t).total_seconds() < 300
            except Exception:
                pass
        if online:
            d["online"] += 1
        else:
            d["offline"] += 1
        # exit node advertised?
        if dev.get("exitNodeOption"):
            d["exit_nodes"].append(dev.get("hostname", "?"))
        # key expiry (skip devices with expiry disabled)
        if not dev.get("keyExpiryDisabled") and dev.get("expires"):
            try:
                ex = _dt.datetime.strptime(dev["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.UTC)
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
    return d


def _lc_get_jwt(api_key, oid):
    data = urllib.parse.urlencode({"secret": api_key, "oid": oid}).encode()
    r = urllib.request.Request("https://jwt.limacharlie.io", data=data,
                               headers={"Content-Type": "application/x-www-form-urlencoded"},
                               method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=TIMEOUT, context=CTX).read().decode())["jwt"]


def _lc_unwrap(raw):
    """LimaCharlie Insight returns gzip+base64 JSON when is_compressed=true."""
    if not raw:
        return []
    import zlib as _zlib
    try:
        return json.loads(_zlib.decompress(base64.b64decode(raw), 16 + _zlib.MAX_WBITS).decode())
    except Exception:
        return []


def collect_limacharlie():
    """Read-only LimaCharlie sensor/detection summary.

    Only uses GET endpoints:
      - /v1/sensors/{oid}
      - /v1/sensors/{oid}?is_online_only=true
      - /v1/insight/{oid}/detections
    No tasking, isolation, tags, policy, or mutation endpoints. Anton approves.
    """
    api_key = _env_first("LIMACHARLIE_API_KEY", "LIMA_CHARLIE_API_KEY", "LC_API_KEY")
    oid = _env_first("LIMACHARLIE_OID", "LIMACHARLIE_ORG_OID", "LIMACHARLIE_ORG_ID", "LIMACHARLIE_ORG", "LIMA_CHARLIE_OID", "LIMA_CHARLIE_ORG_OID", "LIMA_CHARLIE_ORG_ID", "LC_OID")
    if not api_key or not oid:
        present = [k for k in ("LIMACHARLIE_API_KEY", "LIMA_CHARLIE_API_KEY", "LC_API_KEY",
                               "LIMACHARLIE_OID", "LIMACHARLIE_ORG_OID", "LIMACHARLIE_ORG_ID", "LIMACHARLIE_ORG",
                               "LIMA_CHARLIE_OID", "LIMA_CHARLIE_ORG_OID", "LIMA_CHARLIE_ORG_ID", "LC_OID") if E.get(k)]
        note = "LimaCharlie creds not set"
        if present:
            note = "LimaCharlie creds incomplete: " + ", ".join(present)
        return {"state": "degraded", "note": note,
                "total": 0, "online": 0, "offline": 0,
                "detections_24h": None, "top": [], "offline_hosts": []}

    jwt = _lc_get_jwt(api_key, oid)
    auth = {"Authorization": f"Bearer {jwt}"}
    base = "https://api.limacharlie.io/v1"

    def get_all_sensors(online_only=False):
        sensors = []
        token = None
        # LimaCharlie paginates with continuation_token. Hard cap prevents an
        # accidental infinite loop if the API changes shape.
        for _ in range(20):
            qp = {"limit": "500"}
            if token:
                qp["continuation_token"] = token
            if online_only:
                qp["is_online_only"] = "true"
            url = f"{base}/sensors/{urllib.parse.quote(oid)}?{urllib.parse.urlencode(qp)}"
            res = jget(url, auth)
            sensors.extend(res.get("sensors", []))
            token = res.get("continuation_token")
            if not token:
                break
        return sensors

    all_sensors = get_all_sensors(False)
    online_sensors = get_all_sensors(True)
    total = len(all_sensors)
    online = len(online_sensors)
    online_sids = {str(s.get("sid", "")) for s in online_sensors if s.get("sid")}
    offline = max(0, total - online)
    offline_hosts = []
    for s in all_sensors:
        sid = str(s.get("sid", ""))
        if sid not in online_sids:
            offline_hosts.append(s.get("hostname") or sid[:8] or "unknown")
    offline_hosts = sorted(offline_hosts)[:5]

    d = {"state": "ok", "total": total, "online": online, "offline": offline,
         "detections_24h": None, "top": [], "offline_hosts": offline_hosts}
    if total == 0:
        d["state"] = "degraded"
        d["note"] = "no sensor data returned"
    elif offline:
        d["state"] = "warn"

    # Recent detections from Insight. If the key lacks Insight perms or the
    # tenant has no Insight retention, degrade instead of showing fake-green.
    try:
        end = int(time.time())
        start = end - 86400
        detects = []
        cursor = "-"
        for _ in range(10):
            qp = {"start": str(start), "end": str(end), "cursor": cursor,
                  "is_compressed": "true", "limit": "200"}
            url = f"{base}/insight/{urllib.parse.quote(oid)}/detections?{urllib.parse.urlencode(qp)}"
            res = jget(url, auth)
            batch = _lc_unwrap(res.get("detects", ""))
            if isinstance(batch, dict):
                batch = list(batch.values())
            detects.extend(batch or [])
            cursor = res.get("next_cursor")
            if not cursor:
                break
        d["detections_24h"] = len(detects)
        cats = Counter()
        for det in detects:
            if not isinstance(det, dict):
                continue
            cats[det.get("cat") or det.get("name") or "uncategorized"] += 1
        d["top"] = [[k, v] for k, v in cats.most_common(3)]
        if d["detections_24h"] and d["state"] == "ok":
            d["state"] = "warn"
    except Exception as e:
        d["detections_24h"] = None
        d["detect_note"] = f"detections unavailable: {type(e).__name__}"
        if d["state"] == "ok":
            d["state"] = "degraded"
    return d


def collect_wgdashboard():
    """WGDashboard. Real auth flow is POST /api/authenticate (cookie jar) then
    GET /api/getWireguardConfigurations. Each config returns ConnectedPeers,
    TotalPeers and Status (True = interface up). Aggregates across all configs."""
    base = (E.get("WGDASHBOARD_URL") or E.get("WG_URL") or "").strip().rstrip("/")
    user = (E.get("WGDASHBOARD_USERNAME") or E.get("WG_USERNAME") or "").strip()
    pw = (E.get("WGDASHBOARD_PASSWORD") or E.get("WG_PASSWORD") or "").strip()
    if not base or not user or not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "WGDashboard creds not set",
                "connected": 0, "total_peers": 0, "interfaces": []}
    d = {"state": "ok", "connected": 0, "total_peers": 0,
         "ifaces_up": 0, "ifaces_total": 0, "interfaces": []}
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPCookieProcessor(cj))

    def call(path, data=None, method="GET"):
        h = {}
        if isinstance(data, dict):
            data = json.dumps(data).encode()
            h["Content-Type"] = "application/json"
        r = urllib.request.Request(base + path, data=data, headers=h, method=method)
        return json.loads(op.open(r, timeout=TIMEOUT).read().decode("utf-8", "replace"))

    auth = call("/api/authenticate", {"username": user, "password": pw}, "POST")
    if not auth.get("status"):
        raise RuntimeError("WGDashboard auth failed: " + str(auth.get("message"))[:80])
    confs = call("/api/getWireguardConfigurations").get("data", [])
    d["ifaces_total"] = len(confs)
    for c in confs:
        up = bool(c.get("Status"))
        cp = int(c.get("ConnectedPeers", 0) or 0)
        tp = int(c.get("TotalPeers", 0) or 0)
        d["connected"] += cp
        d["total_peers"] += tp
        if up:
            d["ifaces_up"] += 1
        d["interfaces"].append({"name": c.get("Name", "?"), "up": up,
                                "connected": cp, "total": tp,
                                "addr": c.get("Address", "?")})
    d["interfaces"].sort(key=lambda x: x["name"])
    if d["ifaces_total"] and d["ifaces_up"] < d["ifaces_total"]:
        d["state"] = "warn"
    return d

def _fmt_duration(sec):
    try:
        sec = int(sec or 0)
    except Exception:
        sec = 0
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def collect_wan_health():
    """Read-only WAN health from UniFi Network health endpoint."""
    base_host = E.get("UNIFI_URL", "https://10.10.10.1").strip().rstrip("/")
    user = E.get("UNIFI_USERNAME", "").strip()
    pw = E.get("UNIFI_PASSWORD", "").strip()
    if not base_host or not user or not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "UniFi creds not set", "status": "?",
                "latency": None, "uptime": None, "down_mbps": None, "up_mbps": None}
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPCookieProcessor(cj))
    op.open(urllib.request.Request(
        f"{base_host}/api/auth/login",
        data=json.dumps({"username": user, "password": pw}).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=TIMEOUT)
    csrf = None
    tok = next((c.value for c in cj if c.name == "TOKEN"), None)
    if tok:
        try:
            part = tok.split(".")[1]
            part += "=" * (-len(part) % 4)
            csrf = json.loads(base64.urlsafe_b64decode(part)).get("csrfToken")
        except Exception:
            pass
    hdr = {"Content-Type": "application/json"}
    if csrf:
        hdr["X-CSRF-Token"] = csrf
    net = base_host + "/proxy/network/api/s/default"
    r = urllib.request.Request(net + "/stat/health", headers=hdr)
    health = json.loads(op.open(r, timeout=TIMEOUT).read().decode("utf-8", "replace")).get("data", [])
    wan = next((h for h in health if h.get("subsystem") == "wan"), {})
    www = next((h for h in health if h.get("subsystem") == "www"), {})
    status = wan.get("status") or www.get("status") or "?"
    d = {"state": "ok" if status == "ok" else "crit", "status": status,
         "wan_ip": wan.get("wan_ip", "?"), "gateway": wan.get("gw_name", "?"),
         "latency": www.get("latency"), "uptime": www.get("uptime"),
         "down_mbps": www.get("xput_down"), "up_mbps": www.get("xput_up")}
    if d["latency"] is None:
        d["state"] = "degraded" if d["state"] == "ok" else d["state"]
        d["note"] = "WAN latency unavailable"
    elif float(d["latency"] or 0) >= 100 and d["state"] == "ok":
        d["state"] = "warn"
    if d["uptime"] is not None and int(d["uptime"] or 0) < 3600 and d["state"] == "ok":
        d["state"] = "warn"
    return d


SOURCES = [
    ("proxmox", collect_proxmox),
    ("hyperv", collect_hyperv),
    ("system_tools", collect_system_tools_suite),
    ("smart", collect_smart_health),
    ("docker", collect_docker),
    ("pbs", collect_pbs),
    ("kuma", collect_uptime_kuma),
    ("crowdsec", collect_crowdsec),
    ("wazuh", collect_wazuh),
    ("malware_sources", collect_malware_sources),
    ("unifi", collect_unifi),
    ("wan", collect_wan_health),
    ("adguard", collect_adguard),
    ("urbackup", collect_urbackup),
    ("qnap", collect_qnaps),
    ("homeassistant", collect_homeassistant),
    ("adguard2", collect_adguard2),
    ("cloudflare", collect_cloudflare),
    ("npm", collect_npm),
    ("tailscale", collect_tailscale),
    ("wgdashboard", collect_wgdashboard),
    ("limacharlie", collect_limacharlie),
    ("plex", collect_plex),
    ("tautulli", collect_tautulli),
    ("sonarr", collect_sonarr),
    ("radarr", collect_radarr),
    # Lidarr stays available in Add Card, but is not collected/rendered in the default dashboard.
    ("sabnzbd", collect_sabnzbd),
    ("seerr", collect_seerr),
    ("prowlarr", collect_prowlarr),
]


def gather():
    data = {}
    for key, fn in SOURCES:
        try:
            data[key] = fn()
        except Exception as e:
            data[key] = {"state": "error",
                         "error": f"{type(e).__name__}: {str(e)[:140]}"}
    return data


# ============================ HEALTH SCORE STORAGE ============================

HEALTH_LABELS = {
    "proxmox": "Proxmox", "hyperv": "Hyper-V", "smart": "SMART / Disk Health",
    "docker": "Docker / Portainer", "pbs": "PBS Backups", "kuma": "Uptime Kuma",
    "urbackup": "URBackup", "homeassistant": "Home Assistant", "qnap": "QNAP Storage",
    "crowdsec": "CrowdSec", "wazuh": "Wazuh SIEM", "malware_sources": "Malware Detect",
    "unifi": "UniFi UDM-SE", "wan": "WAN / Internet", "adguard": "AdGuard DNS1",
    "adguard2": "AdGuard DNS2", "cloudflare": "Cloudflare", "npm": "Nginx Proxy Manager",
    "tailscale": "Tailscale", "wgdashboard": "WGDashboard", "limacharlie": "LimaCharlie",
    "plex": "Plex", "tautulli": "Tautulli", "sonarr": "Sonarr", "radarr": "Radarr",
    "sabnzbd": "SABnzbd", "seerr": "Overseerr", "prowlarr": "Prowlarr",
}

HEALTH_CATEGORIES = {
    "proxmox": "Infrastructure", "hyperv": "Infrastructure", "smart": "Infrastructure",
    "docker": "Infrastructure", "pbs": "Infrastructure", "kuma": "Infrastructure",
    "urbackup": "Infrastructure", "homeassistant": "Infrastructure",
    "crowdsec": "Security", "wazuh": "Security", "malware_sources": "Security",
    "adguard": "Security", "adguard2": "Security", "limacharlie": "Security",
    "unifi": "Network", "wan": "Network", "cloudflare": "Network", "npm": "Network",
    "tailscale": "Network", "wgdashboard": "Network",
    "plex": "Media", "tautulli": "Media", "sonarr": "Media", "radarr": "Media",
    "sabnzbd": "Media", "seerr": "Media", "prowlarr": "Media",
    "qnap": "Storage",
}


def _health_status(state):
    return "pass" if state == "ok" else "fail"


def _health_value(key, d):
    try:
        if key == "docker":
            return f'{d.get("running", 0)}/{d.get("total", 0)} containers'
        if key == "kuma":
            return f'{d.get("up", 0)}/{d.get("total", 0)} monitors up'
        if key == "pbs":
            return f'{d.get("ok", 0)} ok / {d.get("fail", 0)} fail tasks'
        if key == "urbackup":
            return f'{d.get("online", 0)}/{d.get("total", 0)} clients online'
        if key == "smart":
            return f'{d.get("passed", 0)}/{d.get("checked", 0)} disks passed'
        if key == "proxmox":
            return f'{d.get("vms_running", 0)}/{d.get("vms_total", 0)} VMs running'
        if key == "hyperv":
            return f'{d.get("running", 0)}/{d.get("vm_count", 0)} VMs running'
        if key == "homeassistant":
            return f'{d.get("entities", 0)} entities / {d.get("unavailable", 0)} unavailable'
        if key == "wazuh":
            return f'{d.get("active", 0)}/{d.get("total", 0)} agents online'
        if key == "crowdsec":
            return f'{d.get("bans", 0)} active bans'
        if key in ("adguard", "adguard2"):
            return f'{d.get("queries", 0):,} queries / {d.get("block_pct", 0):.1f}% blocked'
        if key == "wan":
            lat = d.get("latency")
            return f'{str(d.get("status", d.get("wan", "?"))).upper()} / {lat}ms' if lat is not None else str(d.get("status", "?"))
        if key == "unifi":
            return f'{str(d.get("wan", "?")).upper()} / {d.get("clients", 0)} clients'
        if key == "cloudflare":
            return f'{d.get("requests", 0):,} requests / {d.get("threats", 0):,} threats'
        if key == "npm":
            return f'{d.get("enabled", 0)}/{d.get("hosts", 0)} proxy hosts enabled'
        if key == "tailscale":
            return f'{d.get("online", 0)}/{d.get("total", 0)} devices online'
        if key == "wgdashboard":
            return f'{d.get("connected", 0)}/{d.get("peers", d.get("total", 0))} peers connected'
        if key == "limacharlie":
            return f'{d.get("online", 0)}/{d.get("total", 0)} sensors online'
        if key == "qnap":
            units = d.get("units", [])
            bad = sum(1 for u in units if u.get("state") not in ("ok", None))
            return f'{len(units) - bad}/{len(units)} NAS healthy'
        if key in ("sonarr", "radarr"):
            return f'{d.get("queue", 0)} queued / {d.get("missing", 0)} missing'
        if key == "prowlarr":
            return f'{d.get("healthy", 0)}/{d.get("enabled", d.get("total", 0))} indexers healthy'
        if key == "sabnzbd":
            return f'{d.get("status", "?")} / {d.get("queue", 0)} queued'
        if key in ("plex", "tautulli", "seerr"):
            return d.get("note") or d.get("error") or str(d.get("state", "?"))
    except Exception:
        pass
    return d.get("note") or d.get("error") or str(d.get("state", "unknown"))


def build_health_summary(data, now_epoch):
    """Aggregate NOC Health Score from the requested monitored checks."""
    checks = []
    def add(key, service, category, passed, total, detail=""):
        total_i = int(total or 0)
        passed_i = max(0, min(int(passed or 0), total_i)) if total_i else 0
        failed_i = max(0, total_i - passed_i)
        status = "pass" if failed_i == 0 and total_i > 0 else "fail"
        checks.append({"key": key, "service": service, "category": category,
                       "status": status, "state": "ok" if status == "pass" else "crit",
                       "current_value": f"{passed_i}/{total_i}", "passed": passed_i,
                       "total": total_i, "failed": failed_i, "detail": detail,
                       "last_updated": int(now_epoch)})
    P = data.get("proxmox", {})
    add("proxmox", "Proxmox VMs", "Infrastructure", P.get("vms_running", 0), P.get("vms_total", 0), ", ".join(P.get("down_vms", [])[:6]))
    D = data.get("docker", {})
    docker_total = int(D.get("total", 0) or 0); docker_bad = len(D.get("bad", []) or [])
    add("docker", "Docker Containers", "Infrastructure", max(0, docker_total - docker_bad), docker_total, "; ".join(D.get("bad", [])[:6]))
    K = data.get("kuma", {})
    add("kuma", "Uptime Kuma Monitors", "Monitoring", K.get("up", 0), K.get("total", 0), ", ".join(K.get("down", [])[:6]))
    B = data.get("pbs", {})
    pbs_ok = int(B.get("ok", 0) or 0); pbs_fail = int(B.get("fail", 0) or 0); pbs_run = int(B.get("run", 0) or 0)
    add("pbs", "PBS Tasks", "Backup", pbs_ok + pbs_run, pbs_ok + pbs_fail + pbs_run, f"{pbs_fail} failed task(s)" if pbs_fail else "")
    U = data.get("urbackup", {})
    clients = U.get("clients", []) or []
    ub_total = int(U.get("total", 0) or len(clients) or 0)
    ub_good = sum(1 for c in clients if c.get("state") == "ok") if clients else int(U.get("online", 0) or 0)
    add("urbackup", "UrBackup Clients", "Backup", ub_good, ub_total, "; ".join(U.get("problems", [])[:6]))
    W = data.get("wazuh", {})
    add("wazuh", "Wazuh Agents", "Security", W.get("active", 0), W.get("total", 0), ", ".join(W.get("down", [])[:6]))
    checks.sort(key=lambda x: x["service"])
    total = sum(c["total"] for c in checks)
    passed = sum(c["passed"] for c in checks)
    failed = total - passed
    score = round((passed / total) * 100) if total else 0
    counts = {c["service"]: {"pass": c["passed"], "fail": c["failed"], "total": c["total"]} for c in checks}
    return {"timestamp": int(now_epoch), "score": score, "total": total,
            "passed": passed, "failed": failed, "category_counts": counts,
            "checks": checks}


def _health_db():
    os.makedirs(os.path.dirname(HEALTH_DB_FILE), exist_ok=True)
    conn = sqlite3.connect(HEALTH_DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            score REAL NOT NULL,
            total INTEGER NOT NULL,
            passed INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            category_counts TEXT NOT NULL,
            checks_json TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_snapshots_ts ON health_snapshots(ts)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            service_key TEXT NOT NULL,
            service TEXT NOT NULL,
            category TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            message TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_incidents_ts ON health_incidents(ts)")
    return conn


def record_health_snapshot(summary):
    conn = _health_db()
    try:
        prev = {}
        row = conn.execute("SELECT checks_json FROM health_snapshots ORDER BY ts DESC LIMIT 1").fetchone()
        if row:
            for chk in json.loads(row[0] or "[]"):
                prev[chk.get("key")] = chk
        for chk in summary["checks"]:
            old = prev.get(chk["key"])
            if old and old.get("status") != chk.get("status"):
                local = time.strftime("%H:%M", time.localtime(summary["timestamp"]))
                if chk["status"] == "pass":
                    msg = f'{chk["service"]} recovered at {local}'
                else:
                    msg = f'{chk["service"]} went unhealthy at {local}'
                conn.execute("""
                    INSERT INTO health_incidents
                    (ts, service_key, service, category, from_status, to_status, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (summary["timestamp"], chk["key"], chk["service"], chk["category"],
                      old.get("status"), chk.get("status"), msg))
        conn.execute("""
            INSERT INTO health_snapshots
            (ts, score, total, passed, failed, category_counts, checks_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (summary["timestamp"], summary["score"], summary["total"], summary["passed"],
              summary["failed"], json.dumps(summary["category_counts"], separators=(",", ":")),
              json.dumps(summary["checks"], separators=(",", ":"))))
        cutoff = int(time.time()) - 31 * 86400
        conn.execute("DELETE FROM health_snapshots WHERE ts < ?", (cutoff,))
        conn.execute("DELETE FROM health_incidents WHERE ts < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()


# ============================ TREND / HISTORY STORAGE ============================
STATE_DIR = os.path.expanduser("~/.hermes/state")
TRENDS_FILE = os.path.join(STATE_DIR, "dashboard_trends.json")
KUMA_HIST_HOURS = 24
DAILY_KEEP = 30


def load_trends():
    try:
        with open(TRENDS_FILE, encoding="utf-8") as f:
            t = json.load(f)
    except Exception:
        t = {}
    t.setdefault("daily", {})          # {"YYYY-MM-DD": {metric: value}}
    t.setdefault("kuma_history", {})   # {"monitor": [[epoch, status], ...]}
    t.setdefault("wan_history", [])    # [[epoch, latency_ms, down_mbps, up_mbps, status], ...]
    return t


def update_trends(data, now_epoch):
    """Record a daily snapshot (latest-wins) for CrowdSec/AdGuard and append a
    Kuma per-monitor status sample. Prune to retention windows. Returns the
    updated trends dict (also persisted atomically)."""
    t = load_trends()
    day = time.strftime("%Y-%m-%d", time.localtime(now_epoch))

    C = data.get("crowdsec", {})
    A = data.get("adguard", {})
    rec = t["daily"].get(day, {})
    if C.get("state") != "error":
        rec["crowdsec_bans"] = C.get("bans", rec.get("crowdsec_bans", 0))
        rec["crowdsec_local"] = C.get("local_bans", rec.get("crowdsec_local", 0))
    if A.get("state") != "error":
        rec["adguard_blocked"] = A.get("blocked", rec.get("adguard_blocked", 0))
        rec["adguard_queries"] = A.get("queries", rec.get("adguard_queries", 0))
        rec["adguard_block_pct"] = A.get("block_pct", rec.get("adguard_block_pct", 0))
    A2 = data.get("adguard2", {})
    if A2.get("state") not in ("error", "degraded"):
        rec["adguard2_blocked"] = A2.get("blocked", rec.get("adguard2_blocked", 0))
        rec["adguard2_queries"] = A2.get("queries", rec.get("adguard2_queries", 0))
        rec["adguard2_block_pct"] = A2.get("block_pct", rec.get("adguard2_block_pct", 0))
    t["daily"][day] = rec
    # prune daily
    for k in sorted(t["daily"].keys())[:-DAILY_KEEP]:
        del t["daily"][k]

    # Kuma history: append current status per monitor, keep last 24h
    K = data.get("kuma", {})
    if K.get("state") != "error" and (K.get("up") or K.get("total")):
        # rebuild status map from down/other + total: easier to store explicitly
        statuses = K.get("status_map")
        if statuses:
            cutoff = now_epoch - KUMA_HIST_HOURS * 3600
            for name, val in statuses.items():
                hist = t["kuma_history"].setdefault(name, [])
                hist.append([int(now_epoch), int(val)])
                t["kuma_history"][name] = [h for h in hist if h[0] >= cutoff]
            # drop monitors no longer present
            for gone in [m for m in t["kuma_history"] if m not in statuses]:
                t["kuma_history"][gone] = [h for h in t["kuma_history"][gone]
                                           if h[0] >= now_epoch - KUMA_HIST_HOURS * 3600]
                if not t["kuma_history"][gone]:
                    del t["kuma_history"][gone]



    # WAN history: append every regen cycle, keep last 24h. This uses UniFi's
    # read-only WAN health/speedtest fields; zero speed values are retained but
    # rendered as "no recent speedtest" rather than fake throughput.
    WAN = data.get("wan", {})
    if WAN.get("state") not in ("error", "degraded") and WAN.get("latency") is not None:
        cutoff = now_epoch - 24 * 3600
        hist = t.setdefault("wan_history", [])
        hist.append([int(now_epoch), WAN.get("latency"), WAN.get("down_mbps"),
                     WAN.get("up_mbps"), WAN.get("status", "?")])
        t["wan_history"] = [h for h in hist if h[0] >= cutoff]

    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = TRENDS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(t, f)
    os.replace(tmp, TRENDS_FILE)
    return t


# ============================ RENDER ============================

def esc(x):
    return html.escape(str(x))


def pct_color(p):
    if p > 85:
        return "crit"
    if p >= 75:
        return "warn"
    return "ok"


def donut(name, pct):
    """Inline SVG donut gauge."""
    cls = pct_color(pct)
    r = 52
    circ = 2 * 3.14159265 * r
    dash = circ * min(pct, 100) / 100
    return f"""<div class="gauge">
      <svg viewBox="0 0 140 140" class="g-{cls}">
        <circle cx="70" cy="70" r="{r}" class="g-track"/>
        <circle cx="70" cy="70" r="{r}" class="g-val"
                stroke-dasharray="{dash:.1f} {circ:.1f}"
                transform="rotate(-90 70 70)"/>
        <text x="70" y="64" class="g-pct">{pct:.0f}%</text>
        <text x="70" y="86" class="g-lbl">{esc(name)[:14]}</text>
      </svg>
    </div>"""


def card(title, badge_state, body_html, sub=""):
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return f"""<div class="card s-{badge_state}" data-title="{esc(title)}" data-state="{badge_state}" onclick="focusCard(this)" style="cursor:pointer">
      <div class="card-h"><span class="dot"></span><h3>{esc(title)}</h3></div>
      <div class="card-b">{body_html}</div>{sub_html}
    </div>"""


def health_state_for_score(score):
    return "ok" if int(score or 0) >= 95 else ("warn" if int(score or 0) >= 90 else "crit")


def health_score_body(summary):
    """Donut chart + per-category health breakdown shared by the INTEL panel."""
    score = int(summary.get("score", 0))
    state = health_state_for_score(score)
    r = 42
    circ = 2 * 3.14159265 * r
    dash = circ * min(max(score, 0), 100) / 100
    rows = "".join(
        f'<div class="hs-row"><span>{esc(c["service"])}</span><b class="q-{("ok" if c.get("failed",0)==0 else "crit")}">{c.get("passed",0)}/{c.get("total",0)}</b></div>'
        for c in summary.get("checks", [])
    )
    return f"""
      <div class="hs-donut-wrap"><svg viewBox="0 0 110 110" class="hs-donut hs-{state}">
        <circle cx="55" cy="55" r="{r}" class="hs-track"/>
        <circle cx="55" cy="55" r="{r}" class="hs-val" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 55 55)"/>
        <text x="55" y="61" class="hs-pct">{score}%</text>
      </svg></div><div class="hs-breakdown">{rows}</div>"""


def health_score_card(summary):
    """Standalone NOC Health Score grid card intentionally disabled. INTEL owns it."""
    return ""


def _health_history(range_seconds):
    cutoff = int(time.time()) - int(range_seconds)
    try:
        conn = _health_db()
        rows = conn.execute("SELECT ts, score FROM health_snapshots WHERE ts >= ? ORDER BY ts ASC", (cutoff,)).fetchall()
        conn.close()
        return [(int(r[0]), float(r[1])) for r in rows]
    except Exception:
        return []


def _health_incidents(limit=20):
    try:
        conn = _health_db()
        rows = conn.execute("SELECT ts, service, from_status, to_status, message FROM health_incidents ORDER BY ts DESC LIMIT ?", (int(limit),)).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def _svg_line(points, width=520, height=160):
    if len(points) < 2:
        return '<div class="empty">No history yet.</div>'
    step = width / max(1, len(points) - 1)
    coords = []
    for i, (_, v) in enumerate(points):
        x = i * step
        y = height - 8 - ((v / 100) * (height - 16))
        coords.append(f"{x:.1f},{y:.1f}")
    return f'<svg class="hs-line" viewBox="0 0 {width} {height}" preserveAspectRatio="none"><polyline points="{" ".join(coords)}"/></svg>'


def health_modal_html(summary):
    overview = "".join(f'<div class="hs-row"><span>{esc(c["service"])}</span><b>{c.get("passed",0)}/{c.get("total",0)}</b></div>' for c in summary.get("checks", []))
    trends = {"24h": _svg_line(_health_history(86400)), "7d": _svg_line(_health_history(7 * 86400)), "30d": _svg_line(_health_history(30 * 86400))}
    inc_rows = "".join(f'<div class="hs-incident"><span>{time.strftime("%Y-%m-%d %H:%M", time.localtime(int(r[0])))}</span><b>{esc(r[1])}</b><em>{esc(r[2])} → {esc(r[3])}</em><p>{esc(r[4])}</p></div>' for r in _health_incidents(20)) or '<div class="empty">No incidents recorded yet.</div>'
    return f"""<div id="health-modal" class="intel-modal" onclick="if(event.target.id==='health-modal')closeHealthModal()"><div class="intel-modal-box">
      <button class="card-modal-close" onclick="closeHealthModal()">&times;</button><div class="card-modal-title">NOC HEALTH SCORE</div>
      <div class="intel-tabs"><button class="active" onclick="intelTab(event,'hs-overview')">OVERVIEW</button><button onclick="intelTab(event,'hs-trend')">TREND</button><button onclick="intelTab(event,'hs-incidents')">INCIDENTS</button></div>
      <div id="hs-overview" class="intel-tab active"><div class="hs-modal-score q-{health_state_for_score(summary.get("score",0))}">{int(summary.get("score",0))}%</div>{overview}</div>
      <div id="hs-trend" class="intel-tab"><div class="intel-tabs range"><button class="active" onclick="intelRange(event,'r24')">24H</button><button onclick="intelRange(event,'r7')">7D</button><button onclick="intelRange(event,'r30')">30D</button></div><div id="r24" class="intel-range-pane active">{trends['24h']}</div><div id="r7" class="intel-range-pane">{trends['7d']}</div><div id="r30" class="intel-range-pane">{trends['30d']}</div></div>
      <div id="hs-incidents" class="intel-tab">{inc_rows}</div>
    </div></div>"""


def _pct(good, total):
    return round((int(good or 0) / int(total or 0)) * 100) if int(total or 0) else 0


def backup_coverage(data):
    U = data.get("urbackup", {})
    clients = U.get("clients", []) or []
    total = len(clients) or int(U.get("total", 0) or 0)
    file_good = sum(1 for c in clients if c.get("file_recent", c.get("state") == "ok"))
    img_good = sum(1 for c in clients if c.get("image_recent"))
    rows = "".join(f'<div class="intel-list-row"><span>{esc(c.get("name","?"))}</span><em>file {esc(c.get("last_file_backup", c.get("ago", "?")))} · image {esc(c.get("image_days", "never"))}d</em><b class="q-{("ok" if c.get("file_recent") and c.get("image_recent") else "warn")}">●</b></div>' for c in clients)
    return _pct(file_good, total), _pct(img_good, total), rows or '<div class="empty">No UrBackup clients.</div>'


def intelligence_panel_html(data, summary):
    score = int(summary.get("score", 0))
    health_body = health_score_body(summary)
    file_pct, img_pct, backup_rows = backup_coverage(data)
    W, C, LC = data.get("wazuh", {}), data.get("crowdsec", {}), data.get("limacharlie", {})
    waz_high = int(W.get("high_24h", 0) or 0); bans = int(C.get("bans", 0) or 0); lc_det = int(LC.get("detections_24h", 0) or 0)
    sec_score = max(0, 100 - waz_high * 25 - min(25, bans // 25) - min(25, lc_det * 5)); sec_state = "crit" if waz_high else health_state_for_score(sec_score)
    vols = []
    for u in data.get("qnap", {}).get("units", []) or []:
        for v in u.get("volumes", []) or []:
            vols.append((f'{u.get("label","QNAP")} {v.get("name","volume")}', float(v.get("pct", 0) or 0)))
    for ds in data.get("pbs", {}).get("datastores", []) or []:
        vols.append((f'PBS {ds.get("name","datastore")}', float(ds.get("pct", 0) or 0)))
    agg = round(sum(v[1] for v in vols)/len(vols), 1) if vols else 0
    vol_rows = ''.join(f'<div class="intel-storage-row"><div><span>{esc(n)}</span><b>{pct:.0f}%</b></div><div class="intel-bar"><span class="q-{("crit" if pct>85 else "warn" if pct>=70 else "ok")}" style="width:{min(100,max(0,pct)):.0f}%"></span></div></div>' for n,pct in vols) or '<div class="empty">No storage data.</div>'
    certs = []
    for c in data.get("npm", {}).get("cert_list", []) or []:
        certs.append((c.get("name","?"), c.get("days"), c.get("valid", True), "npm"))
    for c in data.get("kuma", {}).get("certs", []) or []:
        if not any(x[0] == c.get("name") for x in certs): certs.append((c.get("name","?"), c.get("days"), c.get("valid", True), "kuma"))
    flags = [n for n,d,v,src in certs if 'portainer' in str(n).lower() and (v is False or (d is not None and d < 0))]
    flag_html = f'<div class="intel-cert-flag">Portainer invalid: {esc(", ".join(flags))}</div>' if flags else ''
    cert_rows = ''.join(f'<div class="intel-list-row"><span>{esc(n)}</span><em>{src}</em><b class="q-{("crit" if (v is False or (d is not None and d<15)) else "warn" if (d is not None and d<=30) else "ok")}">{"INVALID" if v is False else str(d) + "d" if d is not None else "?"}</b></div>' for n,d,v,src in sorted(certs, key=lambda x: (x[2] is not False, 9999 if x[1] is None else x[1]))) or '<div class="empty">No certificate data.</div>'
    return f"""<div id="intel-overlay" class="intel-overlay" onclick="intelOverlayClick(event)"></div><aside id="intel-panel" class="intel-panel"><div class="intel-panel-hdr"><span>📊 NOC INTELLIGENCE</span><button onclick="toggleIntel(false)">&times;</button></div><div class="intel-panel-scroll">
      <div class="intel-card intel-health-card"><button class="intel-card-title" onclick="this.parentNode.classList.toggle('closed')"><span>Health Score</span><b>−</b></button><div class="intel-card-body health-card-body" onclick="openHealthModal(event)">{health_body}</div></div>
      <div class="intel-card intel-backup-card"><button class="intel-card-title" onclick="this.parentNode.classList.toggle('closed')"><span>Backup Coverage</span><b>−</b></button><div class="intel-card-body"><div class="intel-dual-score"><span>File <b class="q-{health_state_for_score(file_pct)}">{file_pct}%</b></span><span>Image <b class="q-{health_state_for_score(img_pct)}">{img_pct}%</b></span></div>{backup_rows}</div></div>
      <div class="intel-card intel-security-card"><button class="intel-card-title" onclick="this.parentNode.classList.toggle('closed')"><span>Security Posture</span><b>−</b></button><div class="intel-card-body"><div class="intel-big-score q-{sec_state}">{sec_score}%</div><div class="hs-row"><span>Wazuh high/crit 24h</span><b>{waz_high}</b></div><div class="hs-row"><span>CrowdSec active bans</span><b>{bans}</b></div><div class="hs-row"><span>LimaCharlie detections 24h</span><b>{lc_det}</b></div></div></div>
      <div class="intel-card intel-storage-card"><button class="intel-card-title" onclick="this.parentNode.classList.toggle('closed')"><span>Storage Health</span><b>−</b></button><div class="intel-card-body"><div class="hs-row"><span>Total aggregate</span><b>{agg}% used</b></div>{vol_rows}</div></div>
      <div class="intel-card intel-cert-card"><button class="intel-card-title" onclick="this.parentNode.classList.toggle('closed')"><span>Certificate Expiry</span><b>−</b></button><div class="intel-card-body">{flag_html}{cert_rows}</div></div>
    </div></aside>{health_modal_html(summary)}"""


def metric(label, value, state=""):
    sc = f" m-{state}" if state else ""
    return f'<div class="metric{sc}"><div class="m-v">{value}</div><div class="m-l">{esc(label)}</div></div>'


def _hb(n):
    """Human-readable bytes."""
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or u == "PB":
            return f"{n:.1f}{u}" if u != "B" else f"{int(n)}B"
        n /= 1024


def _hb_short(n):
    """Compact bytes for tight card metrics: single-letter unit, no decimals
    for values >=100, one decimal below. e.g. 470600000000 -> '438G'."""
    n = float(n or 0)
    for u in ("B", "K", "M", "G", "T", "P"):
        if n < 1024 or u == "P":
            if u == "B":
                return f"{int(n)}B"
            return f"{n:.0f}{u}" if n >= 100 else f"{n:.1f}{u}"
        n /= 1024


def sparkline(values, width=140, height=34, state="ok"):
    """Inline SVG sparkline from a list of numbers."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return '<div class="spark-empty">collecting trend data&hellip;</div>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    step = width / (n - 1)
    pts = []
    for i, v in enumerate(vals):
        x = i * step
        y = height - 4 - (v - lo) / rng * (height - 8)
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    last_x, last_y = pts[-1].split(",")
    area = f"0,{height} " + poly + f" {width},{height}"
    return (f'<svg class="spark sp-{state}" viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none">'
            f'<polygon class="spark-area" points="{area}"/>'
            f'<polyline class="spark-line" points="{poly}"/>'
            f'<circle class="spark-dot" cx="{last_x}" cy="{last_y}" r="2.4"/></svg>')


def kuma_bars(name, history, now_epoch, hours=24):
    """24 hourly colored blocks for one monitor. Each bucket = worst status seen
    that hour. Green=up, red=down, yellow=other, grey=no data."""
    buckets = [None] * hours
    start = now_epoch - hours * 3600
    for ep, st in history:
        if ep < start:
            continue
        idx = int((ep - start) // 3600)
        if idx < 0 or idx >= hours:
            continue
        cur = buckets[idx]
        # severity: down(0) worst, then other(2/3), then up(1)
        sev = {0: 3, 2: 2, 3: 2, 1: 1}.get(int(st), 1)
        prev = {None: 0, "up": 1, "other": 2, "down": 3}.get(cur, 0)
        if sev >= prev:
            buckets[idx] = {3: "down", 2: "other", 1: "up"}[sev]
    cells = ""
    for b in buckets:
        cls = {"up": "b-up", "down": "b-down", "other": "b-other"}.get(b, "b-none")
        cells += f'<span class="hbar {cls}"></span>'
    return f'<div class="hbar-row"><span class="hbar-name">{esc(name)[:20]}</span><span class="hbar-cells">{cells}</span></div>'


def unifi_device_rows(devices):
    rows = ""
    for dv in devices:
        scls = "dv-on" if dv.get("online") else "dv-off"
        rows += (f'<div class="dv {scls}"><span class="dv-dot"></span>'
                 f'<span class="dv-name">{esc(dv["name"])}</span>'
                 f'<span class="dv-kind">{esc(dv["kind"])}</span>'
                 f'<span class="dv-up">{esc(dv["uptime"])}</span></div>')
    return rows or '<div class="empty">No devices reported.</div>'


def render(data, gen_epoch, errors, trends=None, health_summary=None):
    trends = trends or {"daily": {}, "kuma_history": {}}
    health_summary = health_summary or build_health_summary(data, gen_epoch)
    P = data.get("proxmox", {})
    D = data.get("docker", {})
    B = data.get("pbs", {})
    K = data.get("kuma", {})
    C = data.get("crowdsec", {})
    W = data.get("wazuh", {})
    MW = data.get("malware_sources", {})
    U = data.get("unifi", {})
    A = data.get("adguard", {})
    UB = data.get("urbackup", {})
    Q = data.get("qnap", {})
    HA = data.get("homeassistant", {})
    A2 = data.get("adguard2", {})
    CF = data.get("cloudflare", {})
    NPM = data.get("npm", {})
    TS = data.get("tailscale", {})
    WG = data.get("wgdashboard", {})
    PX = data.get("plex", {})
    TA = data.get("tautulli", {})
    SO = data.get("sonarr", {})
    RA = data.get("radarr", {})
    SB = data.get("sabnzbd", {})
    OV = data.get("seerr", {})
    PR = data.get("prowlarr", {})
    LI = data.get("lidarr", {})
    LC = data.get("limacharlie", {})
    SM = data.get("smart", {})
    WAN = data.get("wan", {})
    HV = data.get("hyperv", {})
    STS = data.get("system_tools", {})

    # overall health
    states = [v.get("state", "error") for v in data.values()]
    if "crit" in states or "error" in states:
        overall = "crit"
    elif "warn" in states:
        overall = "warn"
    elif "degraded" in states:
        overall = "degraded"
    else:
        overall = "ok"
    overall_txt = {"ok": "ALL SYSTEMS OPERATIONAL", "warn": "ATTENTION NEEDED",
                   "crit": "CRITICAL", "degraded": "DEGRADED"}[overall]

    dashboard_cfg = load_dashboard_config()
    tz_name = dashboard_cfg.get("timezone") or "UTC"
    date_fmt = dashboard_cfg.get("date_format") or "YYYY-MM-DD"
    clock_fmt = dashboard_cfg.get("clock_format") or "24hr"
    from datetime import datetime as _datetime, timezone as _timezone
    try:
        from zoneinfo import ZoneInfo
        _tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = "UTC"
        _tz = _timezone.utc
    _local_dt = _datetime.fromtimestamp(gen_epoch, _tz)
    _tz_label = _local_dt.tzname() or tz_name
    # Apply date format preference
    if date_fmt == "MM/DD/YYYY":
        _date_str = _local_dt.strftime("%-m/%-d/%Y")
    elif date_fmt == "DD/MM/YYYY":
        _date_str = _local_dt.strftime("%-d/%-m/%Y")
    else:  # YYYY-MM-DD (ISO)
        _date_str = _local_dt.strftime("%Y-%m-%d")
    # Apply clock format preference
    if clock_fmt == "12hr":
        _time_str = _local_dt.strftime("%-I:%M %p")
    else:
        _time_str = _local_dt.strftime("%H:%M")
    # Day of week
    _dow = _local_dt.strftime("%a")
    ts = f"{_dow} {_date_str} {_time_str} {_tz_label}"

    # ---- Row 1: status ----
    prox_running = int(P.get("vms_running", 0) or 0)
    prox_total = int(P.get("vms_total", 0) or 0)
    prox_down = P.get("down_vms") or []
    prox_state = P.get("state", "error")
    if prox_state != "error" and not prox_down and prox_running == prox_total:
        prox_state = "ok"
    prox_body = (metric("VMs", f'{prox_running}/{prox_total}',
                        "crit" if prox_down else "ok")
                 + metric("CPU", f'{P.get("cpu",0):.0f}%')
                 + metric("RAM", f'{P.get("mem_used",0):.0f}/{P.get("mem_total",0):.0f}G'))
    prox_sub = P.get("note") or (("DOWN: " + ", ".join(prox_down)) if prox_down
                                 else f'node {P.get("node","?")} up {P.get("uptime_d",0)}d')
    if P.get("state") == "error":
        prox_sub = P.get("error", "error")

    dock_body = (metric("Running", f'{D.get("running",0)}/{D.get("total",0)}',
                        "warn" if D.get("bad") else "ok")
                 + metric("Envs", D.get("envs", "-")))
    dock_sub = D.get("note") or D.get("error") or (
        ("; ".join(D.get("bad", [])[:3])) if D.get("bad") else "all containers healthy")

    pbs_fail = B.get("fail", 0)
    pbs_mstate = "crit" if pbs_fail else ("warn" if B.get("state") in ("warn", "crit") else "ok")
    pbs_body = (metric("Last Backup", B.get("last_backup", "?"), pbs_mstate)
                + metric("24h Tasks", f'{B.get("ok",0)} ok / {pbs_fail} fail',
                        "crit" if pbs_fail else ""))
    if B.get("datastores"):
        ds = B["datastores"][0]
        pbs_sub = f'datastore {esc(ds["name"])}: {ds["pct"]:.0f}% used'
    else:
        pbs_sub = B.get("error", "")
    if pbs_fail:
        pbs_sub = f'{pbs_fail} FAILED task(s) in 24h' + (f' · {pbs_sub}' if pbs_sub else '')

    if K.get("status_unavailable"):
        kuma_body = (metric("Monitors", f'{K.get("total",0)} active', "")
                     + metric("Status", "n/a", "")
                     + metric("Certs", len(K.get("certs", []))))
    else:
        kuma_body = (metric("Monitors", f'{K.get("up",0)}/{K.get("total",0)} up',
                           "crit" if K.get("down") else ("warn" if K.get("other") else "ok")))
    if K.get("status_unavailable"):
        kuma_sub = K.get("note") or K.get("error") or "monitor status unavailable"
    else:
        kuma_sub = K.get("note") or K.get("error") or (
            ("DOWN: " + ", ".join(K.get("down", []))) if K.get("down")
            else ("all monitors up" if K.get("total", 0) else "no monitor status data"))

    smart_body = (metric("Host Disks", f'{SM.get("passed",0)}/{SM.get("checked",0)} pass',
                         "crit" if SM.get("fail") else ("warn" if SM.get("warn") else ("ok" if SM.get("checked") else "")))
                  + metric("Problems", len(SM.get("problems", [])),
                           "crit" if SM.get("fail") else ("warn" if SM.get("problems") else ""))
                  + metric("VM SMART", "n/a" if SM.get("vm_disks") else "—"))
    if SM.get("problems"):
        smart_sub = "; ".join(SM.get("problems", [])[:2])
    else:
        smart_sub = (SM.get("note") or SM.get("error") or SM.get("vm_note")
                     or "host SMART passed")

    wh = trends.get("wan_history", [])
    lat_series = [h[1] for h in wh if len(h) > 1]
    wan_status = str(WAN.get("status", "?")).upper()
    speed_down = WAN.get("down_mbps")
    speed_up = WAN.get("up_mbps")
    speed_txt = (f'{float(speed_down):.0f}/{float(speed_up):.0f}'
                 if speed_down not in (None, "") and speed_up not in (None, "") and (float(speed_down or 0) or float(speed_up or 0))
                 else "n/a")
    wan_body = (metric("WAN", wan_status,
                       "crit" if WAN.get("state") == "crit" else ("warn" if WAN.get("state") == "warn" else ("ok" if WAN.get("state") == "ok" else "")))
                + metric("Latency", f'{WAN.get("latency")}ms' if WAN.get("latency") is not None else "n/a",
                         "warn" if WAN.get("latency") is not None and float(WAN.get("latency") or 0) >= 100 else "")
                + metric("Speedtest", speed_txt))
    wan_body += f'<div class="trend"><span class="trend-lbl">latency {len(lat_series)} samples / 24h</span>{sparkline(lat_series, state="warn" if WAN.get("state") == "warn" else "ok")}</div>'
    wan_sub = (WAN.get("note") or WAN.get("error")
               or f'{esc(WAN.get("wan_ip","?"))} · uptime {_fmt_duration(WAN.get("uptime"))} · down/up Mbps from UniFi speedtest history')

    # URBackup card
    ub_clients = UB.get("clients", [])
    ub_body = (metric("Clients", f'{UB.get("online",0)}/{UB.get("total",0)} online',
                     "warn" if UB.get("problems") else "ok"))
    if ub_clients:
        rows = []
        for c in ub_clients:
            mc = {"crit": "m-crit", "warn": "m-warn"}.get(c["state"], "")
            badge = "" if c["online"] else " (offline)"
            iss = f' · {c["issues"]} issue(s)' if c.get("issues") else ""
            rows.append(f'<div class="ubrow {mc}"><span class="ub-n">{esc(c["name"])}{badge}</span>'
                        f'<span class="ub-a">{esc(c["ago"])}{iss}</span></div>')
        ub_body += '<div class="ublist">' + "".join(rows) + "</div>"
    ub_sub = (UB.get("note") or UB.get("error")
              or (UB["problems"][0] if UB.get("problems") else "all clients backed up"))

    # Home Assistant card
    ha_body = (metric("Entities", HA.get("entities", 0))
               + metric("Alerts", HA.get("alerts_on", 0),
                       "crit" if HA.get("alerts_on") else "ok")
               + metric("Unavail", HA.get("unavailable", 0),
                       "warn" if HA.get("unavailable", 0) else ""))
    if HA.get("alert_names"):
        ha_sub = "ALERT: " + ", ".join(HA["alert_names"])
    elif HA.get("note") or HA.get("error"):
        ha_sub = HA.get("note") or HA.get("error")
    else:
        ha_sub = (f'{HA.get("domains",0)} domains · {HA.get("notifications",0)} notification(s)')

    # ---- Hyper-V card ----
    hv_vms = HV.get("vms", [])
    hv_run = HV.get("running", 0)
    hv_total = HV.get("vm_count", len(hv_vms))
    hv_stop = HV.get("stopped", 0)
    hv_vm_state = ("crit" if HV.get("state") in ("error",) else
                   "warn" if hv_stop > 0 else
                   "ok" if hv_total > 0 else "")
    # avg CPU across running VMs
    run_cpus = [v.get("cpu", 0) for v in hv_vms if v.get("state") == "Running"]
    avg_cpu = (sum(run_cpus) / len(run_cpus)) if run_cpus else None
    hv_body = (metric("VMs", f"{hv_run}/{hv_total}", hv_vm_state)
               + metric("CPU avg", f"{avg_cpu:.0f}%" if avg_cpu is not None else "—",
                        "crit" if avg_cpu and avg_cpu >= 90 else "warn" if avg_cpu and avg_cpu >= 75 else "")
               + metric("RAM alloc", f'{sum(v.get("mem_gb",0) for v in hv_vms):.1f} GB' if hv_vms else "—"))
    if hv_vms and HV.get("state") != "error":
        vm_rows = []
        for v in hv_vms[:4]:
            dc = "dot-ok" if v["state"] == "Running" else "dot-crit" if v["state"] == "Off" else "dot-warn"
            tail = f'{v["cpu"]:.0f}%' if v["state"] == "Running" and v.get("cpu", 0) > 0 else v["state"]
            vm_rows.append(
                f'<div style="font-size:10px;padding:1px 0;display:flex;align-items:center;gap:4px">'
                f'<span class="dot {dc}" style="width:6px;height:6px;min-width:6px"></span>'
                f'<span>{esc(v["name"])}</span>'
                f'<span style="margin-left:auto;opacity:.6">{tail}</span></div>')
        if len(hv_vms) > 4:
            vm_rows.append(f'<div style="font-size:10px;opacity:.5">+{len(hv_vms)-4} more</div>')
        hv_body += "".join(vm_rows)
    if HV.get("state") == "error":
        hv_sub = esc(HV.get("note", "host unreachable"))
    elif hv_stop > 0:
        down = [v["name"] for v in hv_vms if v.get("state") != "Running"][:3]
        hv_sub = f'OFF: {", ".join(esc(n) for n in down)}'
    else:
        cpus = HV.get("host_cpus", "?")
        mem  = HV.get("host_mem_gb", "?")
        hv_sub = (f'host {cpus} vCPU · {mem} GB' if hv_total > 0
                  else esc(HV.get("note", "all VMs running")))

    row1 = (card("WAN / INTERNET", WAN.get("state", "error"), wan_body, wan_sub)
            + card("PROXMOX", prox_state, prox_body, prox_sub)
            + card("HYPER-V", HV.get("state", "error"), hv_body, hv_sub)
            + card("HOME ASSISTANT", HA.get("state", "error"), ha_body, ha_sub)
            + card("UPTIME KUMA", K.get("state", "error"), kuma_body, kuma_sub)
            + card("DOCKER / PORTAINER", D.get("state", "error"), dock_body, dock_sub)
            + card("PBS BACKUPS", B.get("state", "error"), pbs_body, pbs_sub)
            + card("URBACKUP", UB.get("state", "error"), ub_body, ub_sub)
            + card("SMART / DISK HEALTH", SM.get("state", "error"), smart_body, smart_sub))

    # ---- Row 2: security ----
    daily = trends.get("daily", {})
    days_sorted = sorted(daily.keys())
    cs_series = [daily[d].get("crowdsec_bans") for d in days_sorted]
    cs_local_series = [daily[d].get("crowdsec_local") for d in days_sorted]
    ag_series = [daily[d].get("adguard_blocked") for d in days_sorted]
    ag2_series = [daily[d].get("adguard2_blocked") for d in days_sorted]

    cs_body = (metric("Active Bans", f'{C.get("bans",0):,}')
               + metric("Local Bans", f'{C.get("local_bans",0):,}')
               + metric("Detections 24h",
                        C.get("detections_24h") if C.get("detections_24h") is not None else "n/a"))
    cs_spark = sparkline(cs_series, state="crit")
    cs_body += f'<div class="trend"><span class="trend-lbl">bans {len(days_sorted)}d trend</span>{cs_spark}</div>'
    cs_sub = C.get("error") or (
        ("top: " + ", ".join(f"{k}({v})" for k, v in C.get("top", []))) if C.get("top")
        else "no behavioral bans")

    wz_agent_body = metric("Agents", f'{W.get("active",0)}/{W.get("total",0)} online',
                           "warn" if W.get("down") else "ok")
    if "alerts_24h" in W:
        wz_agent_body += metric("Alerts 24h", f'{W.get("alerts_24h",0):,}')
        wz_agent_body += metric("High/Crit 24h", W.get("high_24h", 0),
                                "crit" if W.get("high_24h") else "ok")
    wz_sub = W.get("error") or (("offline: " + ", ".join(W.get("down", [])))
                                if W.get("down") else "all agents reporting")
    if W.get("alerts_err"):
        wz_sub += f" | indexer: {W['alerts_err']}"

    uni_body = (metric("WAN", esc(U.get("wan", "?")).upper(),
                      "crit" if U.get("wan") != "ok" else "ok")
                + metric("Clients", U.get("clients", 0))
                + metric("IPS 24h", U.get("ips_24h", 0),
                        "warn" if U.get("ips_24h", 0) else ""))
    # WiFi clients per SSID
    if U.get("ssids"):
        ssid_rows = "".join(
            f'<div class="ubrow"><span class="ub-n">{esc(s["name"])}</span>'
            f'<span class="ub-a">{s["clients"]} client{"s" if s["clients"]!=1 else ""}</span></div>'
            for s in U["ssids"])
        uni_body += '<div class="ublist">' + ssid_rows + "</div>"
    # Monthly WAN data usage + PIA VPN: full-width rows (NOT grid metrics) so
    # the values can't collide with each other in the wrapping flex grid.
    info_rows = ""
    if U.get("month_total") is not None:
        mo = f'{_hb_short(U.get("month_rx",0))}↓ / {_hb_short(U.get("month_tx",0))}↑'
        info_rows += (f'<div class="ubrow"><span class="ub-n">Mo. Data</span>'
                      f'<span class="ub-a">{esc(mo)}</span></div>')
    pia = U.get("pia")
    if pia:
        pcls = "" if pia.get("connected") else " m-crit"
        pia_txt = esc(pia.get("status", "?")) + ("" if pia.get("enabled") else " (disabled)")
        info_rows += (f'<div class="ubrow{pcls}"><span class="ub-n">'
                      f'VPN {esc(pia.get("name","PIA"))}</span>'
                      f'<span class="ub-a">{pia_txt}</span></div>')
    if info_rows:
        uni_body += '<div class="ublist">' + info_rows + "</div>"
    if U.get("devices"):
        uni_body += '<div class="dvlist">' + unifi_device_rows(U["devices"]) + "</div>"
    if U.get("latency") is not None:
        uni_sub = f'{esc(U.get("wan_ip","?"))} · {U.get("latency")}ms · ↓{U.get("down_mbps","?")}/↑{U.get("up_mbps","?")} Mbps'
    else:
        uni_sub = U.get("error") or esc(U.get("wan_ip", ""))

    ag_body = (metric("Queries", f'{A.get("queries",0):,}')
               + metric("Blocked", f'{A.get("block_pct",0):.1f}%',
                        "warn" if A.get("block_pct", 0) > 0 else ""))
    ag_spark = sparkline(ag_series, state="warn")
    ag_body += f'<div class="trend"><span class="trend-lbl">blocked {len(days_sorted)}d trend</span>{ag_spark}</div>'
    ag_sub = A.get("error") or f'{A.get("blocked",0):,} blocked · {A.get("avg_ms",0):.1f}ms avg'

    # AdGuard secondary instance (DNS2)
    ag2_body = (metric("Queries", f'{A2.get("queries",0):,}')
                + metric("Blocked", f'{A2.get("block_pct",0):.1f}%',
                         "warn" if A2.get("block_pct", 0) > 0 else ""))
    ag2_spark = sparkline(ag2_series, state="warn")
    ag2_body += f'<div class="trend"><span class="trend-lbl">blocked {len(days_sorted)}d trend</span>{ag2_spark}</div>'
    ag2_sub = (A2.get("note") or A2.get("error")
               or f'{A2.get("blocked",0):,} blocked · {A2.get("avg_ms",0):.1f}ms avg')

    # Cloudflare
    cf_body = (metric("Requests", f'{CF.get("requests",0):,}')
               + metric("Threats", f'{CF.get("threats",0):,}',
                        "warn" if CF.get("threats", 0) else "ok")
               + metric("Bandwidth", _hb(CF.get("bytes", 0))))
    if CF.get("waf_events") is not None:
        cf_body += (metric("WAF 24h", f'{CF.get("waf_events",0):,}')
                    + metric("Blocked 24h", f'{CF.get("waf_blocked",0):,}',
                             "warn" if CF.get("waf_blocked", 0) else ""))
    cf_sub = CF.get("note") or CF.get("error") or (
        f'WAF: {CF.get("waf_note")}' if CF.get("waf_note")
        else "requests/threats/bandwidth today · WAF events 24h")

    # Nginx Proxy Manager
    npm_body = (metric("Proxy Hosts", NPM.get("hosts", 0))
                + metric("Enabled", NPM.get("enabled", 0), "ok")
                + metric("Disabled", NPM.get("disabled", 0),
                         "warn" if NPM.get("disabled", 0) else "")
                + metric("Errored", NPM.get("errored", 0),
                         "crit" if NPM.get("errored", 0) else "")
                + metric("SSL Certs", NPM.get("certs", 0)))
    if NPM.get("cert_list"):
        cert_rows = ""
        for ct in NPM["cert_list"]:
            dys = ct["days"]
            cls = "m-crit" if dys < 7 else ("m-warn" if dys < 21 else "")
            shown = "expired" if dys < 0 else f"{dys}d"
            cert_rows += (f'<div class="ubrow {cls}">'
                          f'<span class="ub-n">{esc(ct["name"])}</span>'
                          f'<span class="ub-a">{shown}</span></div>')
        npm_body += '<div class="ublist">' + cert_rows + "</div>"
    if NPM.get("problems"):
        npm_sub = NPM.get("note") or NPM.get("error") or ("; ".join(NPM["problems"][:4]))
    else:
        npm_sub = NPM.get("note") or NPM.get("error") or "all hosts enabled · no errors"

    # Tailscale
    ts_body = (metric("Devices", TS.get("total", 0))
               + metric("Online", TS.get("online", 0), "ok")
               + metric("Offline", TS.get("offline", 0),
                        "warn" if TS.get("offline", 0) else ""))
    if TS.get("exit_nodes"):
        ts_body += metric("Exit Node", esc(", ".join(TS["exit_nodes"])), "ok")
    if TS.get("devices"):
        ts_rows = "".join(
            f'<div class="ubrow {"" if dv["online"] else "m-warn"}">'
            f'<span class="ub-n">{esc(dv["name"])}{" · exit" if dv.get("exit_node") else ""}</span>'
            f'<span class="ub-a">{"online" if dv["online"] else "offline"}</span></div>'
            for dv in TS["devices"])
        ts_body += '<div class="ublist">' + ts_rows + "</div>"
    if TS.get("note") or TS.get("error"):
        ts_sub = TS.get("note") or TS.get("error")
    elif TS.get("soonest_expiry_days") is not None:
        ts_sub = f'{TS.get("online",0)}/{TS.get("total",0)} online · key expires in {TS["soonest_expiry_days"]}d'
    else:
        ts_sub = f'{TS.get("online",0)}/{TS.get("total",0)} online'

    # LimaCharlie
    lc_det = LC.get("detections_24h")
    lc_body = (metric("Sensors", f'{LC.get("online",0)}/{LC.get("total",0)} online',
                      "warn" if LC.get("offline", 0) else ("ok" if LC.get("total", 0) else ""))
               + metric("Offline", LC.get("offline", 0),
                        "warn" if LC.get("offline", 0) else "")
               + metric("Detections 24h", lc_det if lc_det is not None else "n/a",
                        "warn" if (lc_det or 0) else ("" if lc_det is None else "ok")))
    if LC.get("top"):
        lc_sub = "top: " + ", ".join(f"{k}({v})" for k, v in LC.get("top", []))
    elif LC.get("offline_hosts"):
        lc_sub = "offline: " + ", ".join(LC.get("offline_hosts", []))
    else:
        lc_sub = (LC.get("note") or LC.get("detect_note") or LC.get("error")
                  or "all sensors online · no detections")

    # WGDashboard (WireGuard)
    wg_body = (metric("Peers Conn.", WG.get("connected", 0),
                      "ok" if WG.get("connected", 0) else "")
               + metric("Total Peers", WG.get("total_peers", 0))
               + metric("Interfaces",
                        f'{WG.get("ifaces_up",0)}/{WG.get("ifaces_total",0)} up',
                        "warn" if WG.get("ifaces_total", 0) and WG.get("ifaces_up", 0) < WG.get("ifaces_total", 0) else "ok"))
    if WG.get("interfaces"):
        wg_rows = "".join(
            f'<div class="ubrow {"" if i["up"] else "m-crit"}">'
            f'<span class="ub-n">{esc(i["name"])} ({esc(i["addr"])})</span>'
            f'<span class="ub-a">{"UP" if i["up"] else "DOWN"} · {i["connected"]}/{i["total"]}</span></div>'
            for i in WG["interfaces"])
        wg_body += '<div class="ublist">' + wg_rows + "</div>"
    wg_sub = (WG.get("note") or WG.get("error")
              or f'{WG.get("connected",0)} of {WG.get("total_peers",0)} peers connected')

    # ---- Malware Detection Sources card (ClamAV / YARA / VirusTotal / Defender) ----
    # Explicit three-state tiles (liveness from the data layer, NOT count-inferred):
    #   not live -> "—" (pending) | live & 0 -> "0" (ok) | live & >0 -> count (warn)
    def _mwtile(label, key):
        s = (MW.get("sources") or {}).get(key, {})
        if not s.get("live"):
            return metric(label, "—", "")            # pending install/enrollment
        c = s.get("count")
        if not isinstance(c, int):
            return metric(label, "?", "")            # live but query errored
        return metric(label, f"{c:,}", "warn" if c else "ok")
    mw_body = (_mwtile("ClamAV", "clamav")
               + _mwtile("YARA", "yara")
               + _mwtile("VirusTotal", "virustotal")
               + _mwtile("Defender", "defender"))
    _srcs = MW.get("sources") or {}
    _live_hits = [n for n, k in (("ClamAV", "clamav"), ("YARA", "yara"),
                                 ("VirusTotal", "virustotal"), ("Defender", "defender"))
                  if _srcs.get(k, {}).get("live")
                  and isinstance(_srcs[k].get("count"), int) and _srcs[k]["count"] > 0]
    _pending = [n for n, k in (("ClamAV", "clamav"), ("YARA", "yara"),
                               ("Defender", "defender"))
                if not _srcs.get(k, {}).get("live")]
    if MW.get("note"):
        mw_sub = MW["note"]
    elif _live_hits:
        mw_sub = "detections 24h: " + ", ".join(_live_hits)
    elif _pending:
        mw_sub = "pending: " + ", ".join(_pending)
    else:
        mw_sub = "all sources live · no detections 24h"

    _wz_state_rank = {"ok": 0, "degraded": 1, "warn": 2, "crit": 3, "error": 4}
    wz_combined_state = max((W.get("state", "error"), MW.get("state", "error")),
                            key=lambda s: _wz_state_rank.get(s, 4))
    wz_body = (wz_agent_body
               + '<div class="ublist"><div class="ubrow"><span class="ub-n">Malware Sources</span><span class="ub-a">24h detections</span></div></div>'
               + mw_body)
    wz_combined_sub = wz_sub
    if mw_sub:
        wz_combined_sub += f" | malware: {mw_sub}"

    row2 = (card("UNIFI UDM-SE", U.get("state", "error"), uni_body, uni_sub)
            + card("NGINX PROXY MGR", NPM.get("state", "error"), npm_body, npm_sub)
            + card("CLOUDFLARE", CF.get("state", "error"), cf_body, cf_sub)
            + card("WAZUH SIEM", wz_combined_state, wz_body, wz_combined_sub)
            + card("CROWDSEC", C.get("state", "error"), cs_body, cs_sub)
            + card("LIMACHARLIE (LC)", LC.get("state", "error"), lc_body, lc_sub)
            + card("ADGUARD · DNS1", A.get("state", "error"), ag_body, ag_sub)
            + card("ADGUARD · DNS2", A2.get("state", "error"), ag2_body, ag2_sub)
            + card("TAILSCALE", TS.get("state", "error"), ts_body, ts_sub)
            + card("WGDASHBOARD", WG.get("state", "error"), wg_body, wg_sub))

    # ---- Media row: Plex, Tautulli, Sonarr, Radarr, SABnzbd, Seerr, Prowlarr ----
    # Plex
    plex_body = (metric("Streams", PX.get("streams", 0),
                        "warn" if PX.get("streams", 0) else "ok")
                 + metric("Movies", f'{PX.get("movies",0):,}')
                 + metric("Shows", f'{PX.get("shows",0):,}'))
    plex_sub = (PX.get("note") or PX.get("error")
                or (f'{PX.get("streams",0)} active stream(s)' if PX.get("streams")
                    else "library idle"))

    # Tautulli
    tau_body = (metric("Plays Today", TA.get("plays_today", 0))
                + metric("Streaming", TA.get("streams", 0),
                        "warn" if TA.get("streams", 0) else "ok"))
    if TA.get("top_user"):
        tau_sub = f'top user: {esc(str(TA["top_user"]))} ({TA.get("top_plays",0)} plays)'
    else:
        tau_sub = TA.get("note") or TA.get("error") or "no plays today"

    # Sonarr
    son_body = (metric("Monitored", f'{SO.get("monitored",0):,}')
                + metric("Queue", SO.get("queue", 0),
                        "warn" if SO.get("queue", 0) else "")
                + metric("Missing", SO.get("missing", 0),
                        "warn" if SO.get("missing", 0) else ""))
    son_sub = (SO.get("note") or SO.get("error")
               or f'{SO.get("total",0):,} series total')

    # Radarr
    rad_body = (metric("Monitored", f'{RA.get("monitored",0):,}')
                + metric("Queue", RA.get("queue", 0),
                        "warn" if RA.get("queue", 0) else "")
                + metric("Missing", RA.get("missing", 0),
                        "warn" if RA.get("missing", 0) else ""))
    rad_sub = (RA.get("note") or RA.get("error")
               or f'{RA.get("total",0):,} movies total')

    # SABnzbd
    sab_body = (metric("Queue", SB.get("slots", 0),
                       "warn" if SB.get("slots", 0) else "ok")
                + metric("Speed", f'{SB.get("speed_mbps",0)} MB/s')
                + metric("Today", f'{SB.get("day_gb",0)} GB'))
    sab_sub = (SB.get("note") or SB.get("error")
               or f'status {esc(str(SB.get("status","Idle")))}'
               + (f' · {esc(str(SB.get("timeleft")))} left' if SB.get("slots") else ""))

    # Seerr
    ov_body = (metric("Pending", OV.get("pending", 0),
                     "warn" if OV.get("pending", 0) else "ok")
               + metric("Approved", OV.get("approved", 0))
               + metric("Available", OV.get("available", 0)))
    ov_sub = (OV.get("note") or OV.get("error")
              or f'{OV.get("total",0)} total request(s)')

    # Prowlarr
    pr_body = (metric("Indexers", PR.get("total", 0))
               + metric("Healthy", PR.get("healthy", 0), "ok")
               + metric("Failing", PR.get("failing", 0),
                       "crit" if PR.get("failing", 0) else ""))
    pr_sub = (PR.get("note") or PR.get("error")
              or f'{PR.get("enabled",0)}/{PR.get("total",0)} enabled')

    # Lidarr
    lid_body = (metric("Monitored", f'{LI.get("monitored",0):,}')
                + metric("Queue", LI.get("queue", 0),
                        "warn" if LI.get("queue", 0) else "")
                + metric("Missing", LI.get("missing", 0),
                        "warn" if LI.get("missing", 0) else ""))
    lid_sub = (LI.get("note") or LI.get("error")
               or f'{LI.get("total",0):,} artists total')

    media_row = (card("PLEX", PX.get("state", "error"), plex_body, plex_sub)
                 + card("TAUTULLI", TA.get("state", "error"), tau_body, tau_sub)
                 + card("SONARR", SO.get("state", "error"), son_body, son_sub)
                 + card("RADARR", RA.get("state", "error"), rad_body, rad_sub)
                 + card("SABNZBD", SB.get("state", "error"), sab_body, sab_sub)
                 + card("SEERR", OV.get("state", "error"), ov_body, ov_sub)
                 + card("PROWLARR", PR.get("state", "error"), pr_body, pr_sub))

    sts_url = STS.get("url") or "http://10.10.10.237:10233"
    sts_status = str(STS.get("status", "unknown")).upper()
    sts_body = (metric("Status", sts_status, "ok" if STS.get("state") == "ok" else "warn")
                + metric("Tools", STS.get("tool_count", "?"))
                + metric("Version", esc(str(STS.get("version", "?")))))
    sts_body += (f'<div class="ublist"><a class="svc-link" href="{esc(sts_url)}" '
                 f'target="_blank" rel="noopener" onclick="event.stopPropagation()">'
                 f'Open System Tools Suite &rarr;</a></div>')
    sts_sub = STS.get("note") or STS.get("error") or "tool suite health endpoint responding"
    system_tools_row = card("SYSTEM TOOLS SUITE", STS.get("state", "error"), sts_body, sts_sub)

    # ---- Row 3: storage gauges ----
    gauges = "".join(donut(s["name"], s["pct"]) for s in P.get("storage", []))
    if not gauges:
        gauges = '<div class="empty">No storage volumes visible (Proxmox token ACL).</div>'
    row3 = f'<div class="gauges">{gauges}</div>'

    # ---- Row 4: certs + alerts ----
    cert_tiles = ""
    for c in K.get("certs", []):
        if c["days"] <= CERT_WARN_DAYS or not c["valid"]:
            ccls = "crit" if (c["days"] <= 14 or not c["valid"]) else "warn"
        else:
            ccls = "ok"
        label = "INVALID" if not c["valid"] else f'{c["days"]}d'
        cert_tiles += f'<div class="cert c-{ccls}"><div class="cert-d">{esc(label)}</div><div class="cert-n">{esc(c["name"])}</div></div>'
    if not cert_tiles:
        cert_tiles = '<div class="empty">No TLS certificate data.</div>'

    # active alerts aggregation
    alerts = []
    if P.get("down_vms"):
        alerts += [f"Proxmox VM down: {v}" for v in P["down_vms"]]
    for s in P.get("storage", []):
        if s["pct"] > 85:
            alerts.append(f'Storage {s["name"]} at {s["pct"]:.0f}%')
    for p in SM.get("problems", []):
        alerts.append(f"SMART: {p}")
    if WAN.get("state") in ("warn", "crit"):
        alerts.append(f'WAN: {WAN.get("status","?")} latency={WAN.get("latency","n/a")}ms uptime={_fmt_duration(WAN.get("uptime"))}')
    if D.get("bad"):
        alerts += [f"Docker: {b}" for b in D["bad"][:5]]
    if B.get("fail"):
        alerts.append(f'PBS: {B["fail"]} failed backup task(s) in 24h')
    if B.get("state") == "warn" and not B.get("fail"):
        alerts.append(f'PBS: last backup {B.get("last_backup","?")}')
    for k in K.get("down", []):
        alerts.append(f"Monitor DOWN: {k}")
    for k, st in K.get("other", []):
        alerts.append(f"Monitor {st}: {k}")
    if W.get("down"):
        alerts += [f"Wazuh agent offline: {a}" for a in W["down"]]
    if LC.get("offline_hosts"):
        alerts += [f"LimaCharlie sensor offline: {a}" for a in LC["offline_hosts"]]
    if LC.get("detections_24h"):
        alerts.append(f'LimaCharlie: {LC["detections_24h"]} detection(s) in 24h')
    if U.get("wan") not in ("ok", "?"):
        alerts.append(f'UniFi WAN status: {U.get("wan")}')
    if U.get("ips_24h", 0):
        alerts.append(f'UniFi IPS: {U["ips_24h"]} detection(s) in 24h')
    for c in K.get("certs", []):
        if not c["valid"]:
            alerts.append(f'Cert INVALID: {c["name"]}')
        elif c["days"] <= 14:
            alerts.append(f'Cert expiring: {c["name"]} in {c["days"]}d')
    for key, v in data.items():
        if v.get("state") == "error":
            alerts.append(f'{key} collector error: {v.get("error","")}')
        elif v.get("state") == "degraded" and v.get("note"):
            alerts.append(f'{key}: {v.get("note")}')
    # URBackup problems
    for p in UB.get("problems", []):
        alerts.append(f"URBackup: {p}")
    # QNAP problems
    for u in Q.get("units", []):
        nm = u.get("host", u.get("label", "QNAP"))
        for p in u.get("problems", []):
            alerts.append(f"QNAP {nm}: {p}")
        if u.get("error"):
            alerts.append(f"QNAP {u.get('label','?')} ({u.get('ip','?')}): {u['error']}")
    # Home Assistant
    for an in HA.get("alert_names", []):
        alerts.append(f"Home Assistant alert active: {an}")
    # UniFi offline devices
    for dv in U.get("devices", []):
        if not dv.get("online"):
            alerts.append(f'UniFi device offline: {dv["name"]} ({dv["kind"]})')
    # Cloudflare / NPM
    if CF.get("waf_blocked"):
        alerts.append(f'Cloudflare WAF: {CF["waf_blocked"]:,} request(s) blocked in 24h')
    for p in NPM.get("problems", []):
        alerts.append(f"NPM: {p}")

    if alerts:
        alert_html = "".join(f'<li>{esc(a)}</li>' for a in alerts)
        alert_block = f'<ul class="alerts">{alert_html}</ul>'
    else:
        alert_block = '<div class="empty ok-empty">No active alerts. Nothing on fire.</div>'

    # ---- Ticker bar: aggregate highlights for scrolling info strip ----
    ticker_items = []  # list of (text, css_class)  class: t-crit | t-warn | t-ok | t-info

    if alerts:
        # Determine per-alert severity class for coloring
        _crit_kws = ("crit","down","failed","failed","invalid","offline","smart","error",
                     "unifi device offline","proxmox vm down","monitor down","alert active")
        _warn_kws = ("warn","expiring","urbackup","pbs:","qnap","waf:")
        for a in alerts:
            al = a.lower()
            if any(kw in al for kw in _crit_kws):
                ticker_items.append((a, "t-crit"))
            elif any(kw in al for kw in _warn_kws):
                ticker_items.append((a, "t-warn"))
            else:
                ticker_items.append((a, "t-warn"))
    else:
        # No alerts – show general stats
        # WAN
        if WAN.get("state") == "ok":
            ticker_items.append((
                f'WAN OK \u2022 {esc(WAN.get("wan_ip","?"))} \u2022 latency {WAN.get("latency","n/a")}ms',
                "t-ok"))
        # Docker
        if D.get("state") not in ("error",):
            ticker_items.append((
                f'Containers {D.get("running",0)}/{D.get("total",0)} running',
                "t-ok"))
        # Proxmox
        if P.get("state") not in ("error",):
            ticker_items.append((
                f'Proxmox {P.get("vms_running",0)}/{P.get("vms_total",0)} VMs up \u2022 CPU {P.get("cpu",0):.0f}% \u2022 RAM {P.get("mem_used",0):.0f}/{P.get("mem_total",0):.0f}G',
                "t-ok"))
        # Wazuh
        if W.get("state") not in ("error",):
            ticker_items.append((
                f'Wazuh {W.get("active",0)}/{W.get("total",0)} agents online \u2022 alerts 24h: {W.get("alerts_24h",0):,}',
                "t-info"))
        # CrowdSec
        if C.get("state") not in ("error",):
            ticker_items.append((
                f'CrowdSec {C.get("bans",0):,} active bans \u2022 detections 24h: {C.get("detections_24h","n/a")}',
                "t-info"))
        # LimaCharlie
        if LC.get("state") not in ("error",):
            ticker_items.append((
                f'LimaCharlie {LC.get("online",0)}/{LC.get("total",0)} sensors online',
                "t-ok" if not LC.get("offline") else "t-info"))
        # AdGuard
        if A.get("state") not in ("error",):
            ticker_items.append((
                f'AdGuard \u2022 queries: {A.get("queries",0):,} \u2022 blocked: {A.get("blocked",0):,} ({A.get("blocked_pct",0):.1f}%)',
                "t-info"))
        # PBS
        if B.get("state") not in ("error",):
            ticker_items.append((
                f'PBS last backup: {B.get("last_backup","?")} \u2022 tasks 24h: {B.get("ok",0)} ok / {B.get("fail",0)} fail',
                "t-ok" if not B.get("fail") else "t-warn"))
        # Uptime Kuma
        if K.get("state") not in ("error",) and not K.get("status_unavailable"):
            ticker_items.append((
                f'Kuma {K.get("up",0)}/{K.get("total",0)} monitors up',
                "t-ok"))
        # UniFi IPS
        if U.get("state") not in ("error",) and U.get("ips_24h", 0) == 0:
            ticker_items.append((
                f'UniFi IPS \u2022 0 events in 24h',
                "t-ok"))
        # Home Assistant
        if HA.get("state") not in ("error",):
            ticker_items.append((
                f'Home Assistant \u2022 {HA.get("entities",0)} entities \u2022 {HA.get("unavailable",0)} unavailable',
                "t-info" if HA.get("unavailable",0) else "t-ok"))
        # Cloudflare
        if CF.get("state") not in ("error",):
            ticker_items.append((
                f'Cloudflare WAF \u2022 {CF.get("waf_blocked",0):,} requests blocked 24h',
                "t-info"))
        # SMART
        if SM.get("state") not in ("error",) and not SM.get("fail") and not SM.get("problems"):
            ticker_items.append((
                f'SMART {SM.get("passed",0)}/{SM.get("checked",0)} disks passed',
                "t-ok"))

    # Fallback so the bar is never empty
    if not ticker_items:
        ticker_items.append(("MRDTech NOC \u2022 All data sources unavailable or collecting", "t-info"))

    # Build the scrolling HTML strip (content doubled for seamless loop)
    _sep = '<span class="tk-sep">\u25C6</span>'
    def _tk_span(text, cls):
        return f'<span class="tk-item {cls}">{esc(text)}</span>{_sep}'
    _inner_html = "".join(_tk_span(t, c) for t, c in ticker_items)
    _ticker_content = f'<div class="tk-track"><div class="tk-content" id="tk-content">{_inner_html}{_inner_html}</div></div>'
    # Severity badge
    _badge_cls = "tb-crit" if any(c == "t-crit" for _, c in ticker_items) else \
                 ("tb-warn" if any(c == "t-warn" for _, c in ticker_items) else "tb-ok")
    _badge_txt = "ALERT" if _badge_cls == "tb-crit" else ("WARN" if _badge_cls == "tb-warn" else "INFO")
    _ticker_hidden_cls = "" if dashboard_cfg.get("show_ticker_bar", True) else " ticker-hidden"
    ticker_bar = (f'<div class="ticker-bar{_ticker_hidden_cls}" id="ticker-bar">'
                  f'<div class="tk-badge {_badge_cls}">{_badge_txt}</div>'
                  f'{_ticker_content}'
                  f'</div>')

    # ---- QNAP NAS section ----
    def qnap_card(u):
        st = u.get("state", "error")
        if u.get("error") or u.get("note"):
            body = f'<div class="empty">{esc(u.get("error") or u.get("note"))}</div>'
            title = f'{esc(u.get("label","QNAP"))} · {esc(u.get("ip","?"))}'
            return card(title, st, body)
        # temps
        ct, st_temp = u.get("cpu_temp"), u.get("sys_temp")
        sys_mc = "crit" if (st_temp is not None and st_temp >= 60) else (
            "warn" if (st_temp is not None and st_temp >= 50) else "")
        head = (metric("CPU °C", ct if ct is not None else "?")
                + metric("Sys °C", st_temp if st_temp is not None else "?", sys_mc)
                + metric("Fan", "OK" if u.get("fan_ok") else "FAULT",
                        "" if u.get("fan_ok") else "crit"))
        # volumes
        vol_html = ""
        for v in u.get("volumes", []):
            pcls = pct_color(v["pct"])
            vol_html += (f'<div class="qvol"><div class="qvol-top">'
                         f'<span>{esc(v["name"])}</span>'
                         f'<span class="qvol-pct q-{pcls}">{v["pct"]:.0f}%</span></div>'
                         f'<div class="qbar"><span class="qbar-f q-{pcls}" style="width:{min(v["pct"],100):.0f}%"></span></div>'
                         f'<div class="qvol-cap">{v["used_t"]:.1f} / {v["total_t"]:.1f} TB</div></div>')
        # disks
        disk_html = ""
        for dk in u.get("disks", []):
            hl = dk.get("health", "?")
            ok = hl.upper() in ("OK", "GOOD", "NORMAL")
            dcls = "q-ok" if ok else "q-crit"
            tmp = f'{dk["temp"]}°C' if dk.get("temp") is not None else "—"
            disk_html += (f'<div class="qdisk {dcls}"><span class="qd-dot"></span>'
                          f'<span class="qd-n">{esc(dk["alias"])}</span>'
                          f'<span class="qd-h">{esc(hl)}</span>'
                          f'<span class="qd-t">{esc(tmp)}</span></div>')
        sub = (f'{esc(u.get("model","?"))} · QTS · up {u.get("uptime_d","?")}d'
               + (f' · {len(u.get("disks",[]))} disks' if u.get("disks") else ""))
        body = (head
                + (f'<div class="qsec-l">Volumes</div>{vol_html}' if vol_html else "")
                + (f'<div class="qsec-l">Disk Health</div>{disk_html}' if disk_html else ""))
        title = f'{esc(u.get("host", u.get("label","QNAP")))} · {esc(u.get("ip","?"))}'
        return card(title, st, body, sub)

    qnap_units = Q.get("units", [])
    if qnap_units:
        qnap_cards = "".join(qnap_card(u) for u in qnap_units)
    else:
        qnap_cards = '<div class="empty">No QNAP units configured.</div>'

    # ---- Uptime Kuma 24h history bars ----
    kuma_hist = trends.get("kuma_history", {})
    smap = K.get("status_map", {})
    hist_rows = ""
    if kuma_hist:
        # order: down first, then by name
        def sort_key(name):
            cur = smap.get(name, 1)
            return (0 if cur == 0 else (1 if cur not in (1,) else 2), name.lower())
        for name in sorted(kuma_hist.keys(), key=sort_key):
            hist_rows += kuma_bars(name, kuma_hist[name], gen_epoch, hours=KUMA_HIST_HOURS)
        hist_block = (f'<div class="hbar-head"><span class="hbar-name"></span>'
                      f'<span class="hbar-legend">-24h &rarr; now &nbsp; '
                      f'<span class="hbar b-up"></span>up '
                      f'<span class="hbar b-down"></span>down '
                      f'<span class="hbar b-other"></span>other '
                      f'<span class="hbar b-none"></span>no data</span></div>'
                      + hist_rows)
    else:
        hist_block = '<div class="empty">Collecting uptime history&hellip; bars populate after a few regen cycles.</div>'

    # Build integration status for settings page
    LABELS = {
        "proxmox": "Proxmox", "smart": "SMART/Disk Health", "hyperv": "Hyper-V",
        "docker": "Docker/Portainer", "pbs": "PBS Backups", "kuma": "Uptime Kuma",
        "crowdsec": "CrowdSec", "wazuh": "Wazuh SIEM", "malware_sources": "Malware Detect",
        "unifi": "UniFi UDM-SE", "wan": "WAN/Internet", "adguard": "AdGuard · DNS1",
        "adguard2": "AdGuard · DNS2", "urbackup": "URBackup", "qnap": "QNAP NAS",
        "homeassistant": "Home Assistant", "cloudflare": "Cloudflare",
        "npm": "Nginx Proxy Mgr", "tailscale": "Tailscale", "wgdashboard": "WGDashboard",
        "limacharlie": "LimaCharlie (LC)", "plex": "Plex", "tautulli": "Tautulli",
        "sonarr": "Sonarr", "radarr": "Radarr", "sabnzbd": "SABnzbd",
        "seerr": "Seerr", "prowlarr": "Prowlarr", "lidarr": "Lidarr",
    }
    COMING_SOON = {
        # Homelab
        "pihole": "Pi-hole", "pfsense": "pfSense", "opnsense": "OPNsense",
        "truenas": "TrueNAS", "unraid": "Unraid", "synology": "Synology DSM",
        "jellyfin": "Jellyfin", "emby": "Emby", "nextcloud": "Nextcloud",
        "gitea": "Gitea", "traefik": "Traefik", "caddy": "Caddy",
        "authentik": "Authentik", "authelia": "Authelia",
        "speedtest_tracker": "Speedtest Tracker", "glances": "Glances", "netdata": "Netdata",
        # VPN
        "zerotier": "ZeroTier", "twingate": "Twingate", "netbird": "Netbird",
        "headscale": "Headscale", "pangolin": "Pangolin",
        # Hypervisors
        "vmware": "VMware ESXi/vCenter", "xcpng": "XCP-ng", "libvirt": "libvirt/KVM",
        # Microsoft
        "intune": "Microsoft Intune", "entra": "Entra ID",
        "m365": "M365 Health", "azure_vms": "Azure VMs",
        "exchange": "Exchange Online", "sharepoint": "SharePoint",
        # Security
        "sophos": "Sophos", "meraki": "Cisco Meraki",
        # Networking
        "mikrotik": "MikroTik", "openwrt": "OpenWrt", "snmp": "SNMP Generic",
        # Hardware
        "ipmi": "IPMI", "ilo": "HPE iLO", "idrac": "Dell iDRAC",
        "node_exporter": "Prometheus node_exporter",
        # Cloud
        "aws": "AWS Health", "gcp": "GCP Status",
        "digitalocean": "DigitalOcean", "linode": "Linode/Akamai",
        # Email Security
        "proofpoint": "Proofpoint", "mimecast": "Mimecast",
        "barracuda": "Barracuda", "msdefender_email": "Defender for Office 365",
        # DNS/Web Security
        "cisco_umbrella": "Cisco Umbrella", "zscaler": "Zscaler",
        "cf_gateway": "Cloudflare Gateway",
        # DNS
        "technitium": "Technitium DNS", "blocky": "Blocky DNS", "coredns": "CoreDNS",
        # Endpoint Security
        "crowdstrike": "CrowdStrike", "sentinelone": "SentinelOne",
        "sophos_central": "Sophos Central", "msdefender_ep": "Defender for Endpoint",
        "eset": "ESET", "bitdefender": "Bitdefender GravityZone",
        "malwarebytes": "Malwarebytes ThreatDown",
        # Firewall
        "fortigate": "Fortinet FortiGate", "paloalto": "Palo Alto NGFW",
        "checkpoint": "Check Point", "watchguard": "WatchGuard",
        "sonicwall": "SonicWall", "cisco_asa": "Cisco ASA",
        # SIEM
        "splunk": "Splunk", "elastic": "Elastic/ELK",
        "graylog": "Graylog", "datadog": "Datadog",
        # Vulnerability
        "qualys": "Qualys", "rapid7": "Rapid7 InsightVM",
        "openvas": "Greenbone/OpenVAS",
        # Identity
        "okta": "Okta", "duo": "Duo Security",
        "jumpcloud": "JumpCloud", "onelogin": "OneLogin",
        # Backup
        "veeam": "Veeam", "acronis": "Acronis",
        "commvault": "Commvault", "datto": "Datto BCDR",
        # Ticketing
        "servicenow": "ServiceNow", "zendesk": "Zendesk",
        "freshdesk": "Freshdesk", "connectwise_psa": "ConnectWise Manage",
        # RMM
        "cw_automate": "ConnectWise Automate", "datto_rmm": "Datto RMM",
        "ninjarmm": "NinjaRMM", "atera": "Atera",
        # Containers
        "kubernetes": "Kubernetes", "rancher": "Rancher",
        "nomad": "HashiCorp Nomad",
        # Databases
        "mysql": "MySQL", "postgresql": "PostgreSQL",
        "redis": "Redis", "mongodb": "MongoDB", "mariadb": "MariaDB",
        # Monitoring
        "zabbix": "Zabbix", "nagios": "Nagios",
        "checkmk": "Checkmk", "librenms": "LibreNMS",
        "prtg": "PRTG", "uptimerobot": "Uptime Robot",
        # Storage
        "minio": "MinIO", "ceph": "Ceph",
        # Self-hosted
        "paperless": "Paperless-ngx", "vaultwarden": "Vaultwarden",
        "gotify": "Gotify", "ntfy": "ntfy",
        "bookstack": "BookStack", "wikijs": "Wiki.js",
    }
    integ_list = []
    active_keys = set()
    for key, val in data.items():
        label = LABELS.get(key, key.title())
        state = val.get("state", "error") if isinstance(val, dict) else "error"
        note = ""
        if isinstance(val, dict):
            note = (val.get("error") or val.get("note") or "")[:120]
        integ_list.append({"key": key, "label": label, "state": state, "note": note})
        active_keys.add(key)
    # Append coming-soon items not already active
    for key, label in COMING_SOON.items():
        if key not in active_keys:
            integ_list.append({"key": key, "label": label, "state": "coming_soon", "note": ""})
    # Custom placeholder
    integ_list.append({"key": "custom", "label": "Custom Integration", "state": "custom", "note": ""})
    integ_list.sort(key=lambda x: (0 if x["state"] == "ok" else 1 if x["state"] == "warn" else 2, x["label"]))
    integrations_json = json.dumps(integ_list)

    return PAGE.format(
        ts=esc(ts), overall=overall, overall_txt=overall_txt,
        doc_title=esc(dashboard_cfg["dashboard_title"]),
        dashboard_title=esc(dashboard_cfg["dashboard_title"]),
        dashboard_subtitle=esc(dashboard_cfg["dashboard_subtitle"]),
        dashboard_logo=dashboard_logo_html(dashboard_cfg),
        dashboard_config_json=json.dumps(dashboard_cfg),
        health_current_json=json.dumps(health_summary),
        ticker_bar=ticker_bar,
        row1=row1, row2=row2, media_row=media_row, system_tools_row=system_tools_row, row3=row3,
        qnap_cards=qnap_cards, kuma_history=hist_block,
        cert_tiles=cert_tiles, alert_block=alert_block,
        integrations_json=integrations_json,
        cc_css=_CC_CSS + _ACP_CSS,
        intel_css=INTEL_CSS,
        cc_btn=_ACP_BTN_HTML,
        cc_overlay=_ACP_HTML + "\n" + _CC_OVERLAY_HTML,
        intel_panel=intelligence_panel_html(data, health_summary),
        intel_js=INTEL_JS,
        cc_js=_ACP_JS_TMPL.replace("__ACP_JSON__", _ACP_JSON) + "\n" + _CC_JS_TMPL.replace("__CC_SEED__", _cc_seed_json()).replace("__BCC_SEED__", _bcc_seed_json()),
    )



# ── Add Card Panel — CSS, HTML, JS ────────────────────────────────────────────
import json as _json_acp

_ACP_CARD_TYPES = [
    {"key":"proxmox",        "label":"Proxmox",          "cat":"Infrastructure", "integ":"proxmox"},
    {"key":"docker",         "label":"Docker/Portainer",  "cat":"Infrastructure", "integ":"docker"},
    {"key":"pbs",            "label":"PBS Backups",        "cat":"Infrastructure", "integ":"pbs"},
    {"key":"kuma",           "label":"Uptime Kuma",        "cat":"Infrastructure", "integ":"kuma"},
    {"key":"urbackup",       "label":"URBackup",           "cat":"Infrastructure", "integ":"urbackup"},
    {"key":"hyperv",         "label":"Hyper-V",            "cat":"Infrastructure", "integ":"hyperv"},
    {"key":"smart",          "label":"SMART/Disk Health",  "cat":"Infrastructure", "integ":None},
    {"key":"wazuh",          "label":"Wazuh SIEM",         "cat":"Security",       "integ":"wazuh"},
    {"key":"crowdsec",       "label":"CrowdSec",            "cat":"Security",       "integ":"crowdsec"},
    {"key":"cloudflare",     "label":"Cloudflare",         "cat":"Security",       "integ":"cloudflare"},
    {"key":"limacharlie",    "label":"LimaCharlie",        "cat":"Security",       "integ":"limacharlie"},
    {"key":"malware_sources","label":"Malware Detect",     "cat":"Security",       "integ":None},
    {"key":"cert-expiry",    "label":"TLS Cert Expiry",    "cat":"Security",       "integ":None},
    {"key":"active-alerts",  "label":"Active Alerts",      "cat":"Security",       "integ":None},
    {"key":"unifi",          "label":"UniFi UDM-SE",       "cat":"Network",        "integ":"unifi"},
    {"key":"wan",            "label":"WAN/Internet",        "cat":"Network",        "integ":"unifi"},
    {"key":"adguard",        "label":"AdGuard DNS1",        "cat":"Network",        "integ":"adguard"},
    {"key":"adguard2",       "label":"AdGuard DNS2",        "cat":"Network",        "integ":"adguard2"},
    {"key":"npm",            "label":"Nginx Proxy Mgr",    "cat":"Network",        "integ":"npm"},
    {"key":"tailscale",      "label":"Tailscale",          "cat":"Network",        "integ":"tailscale"},
    {"key":"wgdashboard",    "label":"WGDashboard",        "cat":"Network",        "integ":"wgdashboard"},
    {"key":"qnap",           "label":"QNAP NAS",            "cat":"Storage",        "integ":"qnap"},
    {"key":"proxmox-storage","label":"Proxmox Storage",    "cat":"Storage",        "integ":"proxmox"},
    {"key":"plex",           "label":"Plex",                "cat":"Media",          "integ":"plex"},
    {"key":"tautulli",       "label":"Tautulli",            "cat":"Media",          "integ":"tautulli"},
    {"key":"sonarr",         "label":"Sonarr",              "cat":"Media",          "integ":"sonarr"},
    {"key":"radarr",         "label":"Radarr",              "cat":"Media",          "integ":"radarr"},
    {"key":"lidarr",         "label":"Lidarr",              "cat":"Media",          "integ":"lidarr"},
    {"key":"sabnzbd",        "label":"SABnzbd",             "cat":"Media",          "integ":"sabnzbd"},
    {"key":"seerr",          "label":"Seerr",               "cat":"Media",          "integ":"seerr"},
    {"key":"prowlarr",       "label":"Prowlarr",            "cat":"Media",          "integ":"prowlarr"},
    {"key":"homeassistant",  "label":"Home Assistant",      "cat":"Monitoring",     "integ":"homeassistant"},
    {"key":"kuma-history",   "label":"Uptime History",      "cat":"Monitoring",     "integ":"kuma"},
    {"key":"custom-card",    "label":"Custom Card",         "cat":"Custom",         "integ":None},
]

_ACP_JSON = _json_acp.dumps(_ACP_CARD_TYPES)

_ACP_CSS = """
  /* ── Add Card Panel ── */
  .acp-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.88);
    backdrop-filter:blur(4px);z-index:3000;align-items:center;justify-content:center;padding:20px;box-sizing:border-box;}
  .acp-overlay.open{display:flex;}
  .acp-shell{background:var(--panel);border:1px solid var(--line);border-radius:8px;
    width:min(820px,100%);max-height:88vh;display:flex;flex-direction:column;overflow:hidden;}
  .acp-hdr{display:flex;align-items:center;justify-content:space-between;padding:12px 18px;
    border-bottom:1px solid var(--line);background:var(--panel2);flex-shrink:0;}
  .acp-title{font-size:11px;font-weight:700;letter-spacing:3px;color:var(--green);text-transform:uppercase;}
  .acp-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:0 4px;}
  .acp-close:hover{color:var(--green);}
  .acp-body{overflow-y:auto;padding:16px 18px 20px;}
  .acp-cat-hdr{font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;
    color:var(--green-dim);margin:14px 0 6px;padding-bottom:4px;border-bottom:1px solid var(--line);}
  .acp-cat-hdr:first-child{margin-top:0;}
  .acp-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px;margin-bottom:4px;}
  .acp-card{background:var(--panel2);border:1px solid var(--line);border-radius:5px;
    padding:10px 12px;cursor:pointer;transition:border-color .15s,background .15s;}
  .acp-card:hover{border-color:var(--green-dim);background:rgba(0,255,65,.05);}
  .acp-card.needs-cfg{opacity:.55;cursor:default;}
  .acp-card.needs-cfg:hover{border-color:var(--line);background:var(--panel2);}
  .acp-card-label{font-size:11px;color:var(--txt);font-weight:600;}
  .acp-card-hint{font-size:9px;color:var(--muted);margin-top:3px;}
  .acp-custom-btn{display:block;width:100%;margin-top:14px;padding:10px;border:1px dashed var(--green-dim);
    background:rgba(0,255,65,.05);border-radius:5px;color:var(--green-dim);font-size:11px;
    letter-spacing:2px;text-transform:uppercase;cursor:pointer;font-family:inherit;text-align:center;}
  .acp-custom-btn:hover{border-color:var(--green);color:var(--green);background:rgba(0,255,65,.1);}
  #add-card-btn{display:none;}
"""

_ACP_HTML = """  <!-- Add Card Panel -->
  <div id="acp-overlay" class="acp-overlay" onclick="acpOverlayClick(event)">
    <div class="acp-shell">
      <div class="acp-hdr">
        <div class="acp-title">&#10010; Add Card</div>
        <button class="acp-close" onclick="closeACP()">&times;</button>
      </div>
      <div class="acp-body" id="acp-body"></div>
    </div>
  </div>
"""

_ACP_BTN_HTML = """      <button id="add-card-btn" class="theme-btn" onclick="openACP()" title="Add card (edit mode only)">&#10010; ADD CARD</button>"""

_ACP_JS_TMPL = r"""
  var ACP_CARD_TYPES = __ACP_JSON__;

  window.openACP = function() {
    var ov = document.getElementById('acp-overlay');
    if (!ov) return;
    _acpBuild();
    ov.classList.add('open');
    document.body.style.overflow = 'hidden';
  };
  window.closeACP = function() {
    var ov = document.getElementById('acp-overlay');
    if (ov) ov.classList.remove('open');
    document.body.style.overflow = '';
  };
  window.acpOverlayClick = function(e) {
    var ov = document.getElementById('acp-overlay');
    if (typeof _nocBackdropClick === 'function') {
      if (_nocBackdropClick(e, ov, '.acp-shell')) closeACP();
      return;
    }
    if (e && ov && e.target === ov) closeACP();
  };
  function _acpIsConfigured(integKey) {
    if (!integKey) return true;
    var integ = (typeof INTEGRATIONS !== 'undefined' ? INTEGRATIONS : [])
      .find(function(i) { return i.key === integKey; });
    if (!integ) return false;
    return integ.state !== 'coming_soon' && integ.state !== 'custom' && integ.state !== 'error';
  }
  function _acpBuild() {
    var body = document.getElementById('acp-body');
    if (!body) return;
    var cats = {};
    ACP_CARD_TYPES.forEach(function(ct) {
      if (!cats[ct.cat]) cats[ct.cat] = [];
      cats[ct.cat].push(ct);
    });
    var html = '';
    Object.keys(cats).forEach(function(cat) {
      html += '<div class="acp-cat-hdr">' + cat + '</div><div class="acp-grid">';
      cats[cat].forEach(function(ct) {
        var ok = _acpIsConfigured(ct.integ);
        html += '<div class="acp-card' + (ok ? '' : ' needs-cfg') + '" data-card-key="' + ct.key + '" data-configured="' + ok + '">'
          + '<div class="acp-card-label">' + ct.label + '</div>'
          + '<div class="acp-card-hint">' + (ok ? 'Click to add' : 'Configure in Settings first') + '</div></div>';
      });
      html += '</div>';
    });
    html += '<button class="acp-custom-btn" onclick="closeACP();openCustomCardBuilder(null)">&#9881; Build Custom Card</button>';
    body.innerHTML = html;
    body.onclick = function(e) {
      var card = e.target.closest('.acp-card');
      if (!card || card.dataset.configured === 'false') return;
      if (card.dataset.cardKey === 'custom-card') { closeACP(); openCustomCardBuilder(null); return; }
      _acpAddCard(card.dataset.cardKey);
    };
  }
  function _acpAddCard(key) {
    var existing = document.querySelector('[data-card-id="' + key + '"]');
    if (!existing) {
      document.querySelectorAll('.card h3').forEach(function(h3) {
        if (!existing && h3.textContent.trim().toUpperCase() === key.replace(/-/g,' ').toUpperCase())
          existing = h3.closest('.card');
      });
    }
    if (existing) {
      existing.style.display = '';
      closeACP();
      existing.scrollIntoView({behavior:'smooth',block:'center'});
      return;
    }
    var firstRow = document.querySelector('.row');
    if (!firstRow) { closeACP(); return; }
    var ph = document.createElement('div');
    ph.className = 'card s-degraded'; ph.setAttribute('data-card-id', key);
    ph.innerHTML = '<h3>' + key.replace(/-/g,' ').toUpperCase() + '</h3>'
      + '<div class="sub">Will appear after next dashboard refresh</div>';
    firstRow.appendChild(ph);
    if (document.body.classList.contains('edit-mode')) {
      if (!ph.querySelector('.card-rm-btn')) {
        var rmBtn = document.createElement('button');
        rmBtn.className = 'card-rm-btn'; rmBtn.title = 'Remove card'; rmBtn.textContent = '✕';
        rmBtn.addEventListener('click', function(ev) {
          ev.stopPropagation();
          if (confirm('Remove this card? (Reload page to restore)')) { ph.remove(); persistLayout(); }
        });
        ph.appendChild(rmBtn);
      }
    }
    persistLayout();
    closeACP();
    ph.scrollIntoView({behavior:'smooth',block:'center'});
  }
  var _origTEM2 = window.toggleEditMode;
  window.toggleEditMode = function() {
    var ret = _origTEM2.apply(this, arguments);
    var isEdit = document.body.classList.contains('edit-mode');
    var btn = document.getElementById('add-card-btn');
    if (btn) btn.style.display = isEdit ? 'inline-block' : 'none';
    return ret;
  };
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      var ov = document.getElementById('acp-overlay');
      if (ov && ov.classList.contains('open')) { closeACP(); return; }
    }
  });
"""



# ── Custom Card Builder — CSS, HTML and JS constants ─────────────────────────
# These are passed as substitution values into PAGE.format(), so they may
# contain normal { } braces without escaping.

CUSTOM_CARDS_FILE = os.path.join(
    os.environ.get("NOC_OUT_DIR", os.path.expanduser("~/mrdtech-dashboard")),
    "custom_cards.json"
)
BUILTIN_CARD_CONFIGS_FILE = os.path.join(
    os.environ.get("NOC_OUT_DIR", os.path.expanduser("~/mrdtech-dashboard")),
    "builtin_card_configs.json"
)

def _bcc_seed_json():
    """Load saved built-in card display configs from disk; return JSON object string for JS seed."""
    path = os.path.join(
        os.environ.get("NOC_OUT_DIR", os.path.expanduser("~/mrdtech-dashboard")),
        "builtin_card_configs.json"
    )
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read().strip() or "{}"
        obj = json.loads(raw)
        return json.dumps(obj if isinstance(obj, dict) else {})
    except Exception:
        return "{}"


def _cc_seed_json():
    """Load saved custom card configs from disk; return as JSON string for JS seed."""
    # Re-evaluate path at call time so NOC_OUT_DIR override (set in entrypoint) is respected
    path = os.path.join(
        os.environ.get("NOC_OUT_DIR", os.path.expanduser("~/mrdtech-dashboard")),
        "custom_cards.json"
    )
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or "[]"
    except FileNotFoundError:
        return "[]"
    except Exception:
        return "[]"

_CC_CSS = """
  /* ── Custom Card Builder ── */
  .custom-builder-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:2000;align-items:center;justify-content:center;}
  .custom-builder-overlay.open{display:flex;}
  .custom-builder-shell{background:var(--panel);border:1px solid var(--line);border-radius:8px;width:min(700px,95vw);max-height:88vh;display:flex;flex-direction:column;overflow:hidden;}
  .cb-hdr{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--line);flex-shrink:0;}
  .cb-title-hdr{font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--green);}
  .cb-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:2px 6px;line-height:1;}
  .cb-close:hover{color:var(--green);}
  .cb-body{padding:18px;overflow-y:auto;flex:1;}
  .cb-section-hdr{font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:5px;margin:16px 0 10px;}
  .cb-section-hdr:first-child{margin-top:0;}
  .cb-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
  .cb-field{display:flex;flex-direction:column;gap:4px;}
  .cb-field.span2{grid-column:span 2;}
  .cb-field label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;}
  .custom-builder-shell input,.custom-builder-shell select,.custom-builder-shell textarea{background:var(--panel2);border:1px solid var(--line);color:var(--txt);padding:7px 10px;border-radius:4px;font-size:12px;font-family:inherit;width:100%;box-sizing:border-box;}
  .custom-builder-shell input:focus,.custom-builder-shell select:focus,.custom-builder-shell textarea:focus{outline:none;border-color:var(--green);box-shadow:0 0 0 1px rgba(0,255,65,.16);}
  .cb-field input,.cb-field select{background:var(--panel2);border:1px solid var(--line);color:var(--txt);padding:7px 10px;border-radius:4px;font-size:12px;font-family:inherit;width:100%;box-sizing:border-box;}
  .cb-field input:focus,.cb-field select:focus{outline:none;border-color:var(--green-dim);}
  .cb-field select option{background:var(--panel);}
  .cb-auth-fields{margin-top:8px;display:grid;grid-template-columns:1fr 1fr;gap:10px;}
  .cb-auth-fields .cb-field.span2{grid-column:span 2;}
  .cb-fields-list{display:flex;flex-direction:column;gap:6px;margin-top:8px;}
  .cb-field-row{display:grid;grid-template-columns:1fr 1fr 28px;gap:6px;align-items:center;}
  .cb-field-row input{background:var(--panel2);border:1px solid var(--line);color:var(--txt);padding:6px 8px;border-radius:4px;font-size:11px;font-family:inherit;width:100%;box-sizing:border-box;}
  .cb-rm{background:none;border:1px solid var(--line);color:var(--muted);border-radius:3px;cursor:pointer;font-size:14px;padding:0;width:24px;height:24px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
  .cb-rm:hover{color:var(--crit);border-color:var(--crit);}
  .cb-add-field-btn{background:none;border:1px dashed var(--line);color:var(--muted);border-radius:4px;padding:5px 12px;font-size:11px;cursor:pointer;margin-top:4px;font-family:inherit;width:100%;}
  .cb-add-field-btn:hover{border-color:var(--green-dim);color:var(--green);}
  .cb-thresh-grid{display:grid;grid-template-columns:auto 1fr 1fr;gap:6px 8px;align-items:center;margin-top:8px;}
  .cb-thresh-lbl{font-size:10px;font-weight:700;letter-spacing:1px;white-space:nowrap;}
  .cb-thresh-lbl.g{color:var(--green);}
  .cb-thresh-lbl.y{color:var(--warn);}
  .cb-thresh-lbl.r{color:var(--crit);}
  .cb-thresh-grid select,.cb-thresh-grid input[type=text]{background:var(--panel2);border:1px solid var(--line);color:var(--txt);padding:5px 8px;border-radius:4px;font-size:11px;font-family:inherit;box-sizing:border-box;width:100%;}
  .cb-footer{padding:14px 18px;border-top:1px solid var(--line);display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap;}
  .cb-btn-primary{background:var(--green);color:#000;border:none;border-radius:4px;padding:8px 18px;font-size:11px;font-weight:700;letter-spacing:1px;cursor:pointer;font-family:inherit;}
  .cb-btn-primary:hover{opacity:.85;}
  .cb-btn-secondary{background:none;border:1px solid var(--line);color:var(--muted);border-radius:4px;padding:8px 14px;font-size:11px;cursor:pointer;font-family:inherit;}
  .cb-btn-secondary:hover{border-color:var(--green-dim);color:var(--txt);}
  .cb-msg{font-size:11px;}
  .cb-msg.ok{color:var(--green);}
  .cb-msg.err{color:var(--crit);}
  .cb-hint{font-size:10px;color:var(--muted);margin-bottom:8px;line-height:1.6;}
  .cb-hint code{background:var(--panel2);padding:1px 4px;border-radius:2px;font-family:monospace;}
  #add-custom-card-btn{display:none;}
  .edit-mode #add-custom-card-btn{display:none!important;}
  .custom-card-loading{font-size:11px;color:var(--muted);font-style:italic;}
  .kv-rows{display:flex;flex-direction:column;gap:4px;width:100%;}
  .kv-row{display:flex;justify-content:space-between;align-items:baseline;padding:3px 0;border-bottom:1px solid var(--line);font-size:12px;}
  .kv-row:last-child{border-bottom:none;}
  .kv-lbl{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:1px;}
  .kv-val{color:var(--txt);font-weight:600;}
  .card-edit-btn{position:absolute;top:6px;right:54px;background:var(--panel2);border:1px solid var(--line);color:var(--txt);border-radius:3px;width:22px;height:22px;font-size:11px;cursor:pointer;display:none;align-items:center;justify-content:center;z-index:10;padding:0;}
  .edit-mode .card-edit-btn{display:flex;}
  .card-edit-btn:hover{color:var(--green);border-color:var(--green-dim);}

  /* ── Built-in Card Settings ── */
  .card-gear-btn{display:none;position:absolute;top:4px;right:48px;z-index:11;background:var(--panel2);border:1px solid var(--line);color:var(--txt);width:20px;height:20px;border-radius:3px;font-size:12px;line-height:18px;text-align:center;cursor:pointer;padding:0;}
  .edit-mode .card-gear-btn,.card:hover .card-gear-btn{display:block;}
  .card-gear-btn:hover{color:var(--green);border-color:var(--green-dim);}
  .builtin-card-config-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:2100;align-items:center;justify-content:center;}
  .builtin-card-config-overlay.open{display:flex;}
  .bcc-shell{background:var(--panel);border:1px solid var(--line);border-radius:8px;width:min(760px,95vw);max-height:88vh;display:flex;flex-direction:column;overflow:hidden;}
  .bcc-hdr{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--line);background:var(--panel2);}
  .bcc-title{font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--green);}
  .bcc-close{background:none;border:none;color:var(--muted);font-size:20px;cursor:pointer;padding:2px 6px;line-height:1;}
  .bcc-close:hover{color:var(--green);}
  .bcc-body{padding:18px;overflow:auto;}
  .bcc-section-hdr{font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--green-dim);border-bottom:1px solid var(--line);padding-bottom:5px;margin:16px 0 10px;}
  .bcc-section-hdr:first-child{margin-top:0;}
  .bcc-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px;}
  .bcc-field{display:flex;flex-direction:column;gap:4px;}
  .bcc-field.span2{grid-column:span 2;}
  .bcc-field label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;}
  .bcc-shell input,.bcc-shell select{background:var(--panel2);border:1px solid var(--line);color:var(--txt);padding:7px 10px;border-radius:4px;font-size:12px;font-family:inherit;width:100%;box-sizing:border-box;}
  .bcc-shell input:focus,.bcc-shell select:focus{outline:none;border-color:var(--green);box-shadow:0 0 0 1px rgba(0,255,65,.16);}
  .bcc-rows{display:flex;flex-direction:column;gap:6px;}
  .bcc-row{display:grid;grid-template-columns:26px 1fr 28px 28px;gap:6px;align-items:center;background:var(--panel2);border:1px solid var(--line);border-radius:4px;padding:6px;}
  .bcc-row input[type=checkbox]{width:auto;accent-color:var(--green);}
  .bcc-row-name{font-size:11px;color:var(--txt);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
  .bcc-row button{background:none;border:1px solid var(--line);color:var(--muted);border-radius:3px;cursor:pointer;height:24px;}
  .bcc-row button:hover{border-color:var(--green-dim);color:var(--green);}
  .bcc-footer{padding:14px 18px;border-top:1px solid var(--line);display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
  .builtin-hidden-field{display:none!important;}
"""

_CC_BTN_HTML = """      <button id="add-custom-card-btn" class="theme-btn" onclick="openCustomCardBuilder(null)" title="Add custom card (edit mode only)">&#43; CARD</button>"""

_CC_OVERLAY_HTML = """  <!-- Custom Card Builder overlay -->
  <div id="custom-builder-overlay" class="custom-builder-overlay" onclick="if(event.target===this)closeCustomCardBuilder()">
    <div class="custom-builder-shell">
      <div class="cb-hdr">
        <div class="cb-title-hdr">&#43; Custom Card Builder</div>
        <button class="cb-close" onclick="closeCustomCardBuilder()" title="Close">&times;</button>
      </div>
      <div class="cb-body"><div id="cb-form"></div></div>
      <div class="cb-footer">
        <button class="cb-btn-primary" onclick="saveCustomCard()">&#10003; Save Card</button>
        <button class="cb-btn-secondary" onclick="testCustomCardFetch()">&#9654; Test URL</button>
        <span id="cb-save-msg" class="cb-msg"></span>
      </div>
    </div>
  </div>
  <!-- Built-in Card Settings overlay -->
  <div id="builtin-config-overlay" class="builtin-card-config-overlay" onclick="if(event.target===this)closeBuiltinCardConfig()">
    <div class="bcc-shell">
      <div class="bcc-hdr"><div class="bcc-title">&#9881; Built-in Card Settings</div><button class="bcc-close" onclick="closeBuiltinCardConfig()" title="Close">&times;</button></div>
      <div class="bcc-body"><div id="bcc-form"></div></div>
      <div class="bcc-footer">
        <button class="cb-btn-primary" onclick="saveBuiltinCardConfig()">&#10003; Save Card Settings</button>
        <button class="cb-btn-secondary" onclick="resetBuiltinCardConfig()">Reset Card</button>
        <span id="bcc-save-msg" class="cb-msg"></span>
      </div>
    </div>
  </div>"""

# JS uses __CC_SEED__ as a placeholder replaced at render time (avoids .format escaping)
_CC_JS_TMPL = r"""
  /* ── Custom Card Builder System ── */
  var CUSTOM_CARDS_SEED = __CC_SEED__;
  var CUSTOM_CARDS_KEY  = 'noc-custom-cards';
  var _customCards      = [];
  var _customFetchTimers = {};
  var _builderEditId    = null;

  function _ccLoad() {
    try {
      var stored = JSON.parse(localStorage.getItem(CUSTOM_CARDS_KEY) || '[]');
      _customCards = stored.length ? stored : (CUSTOM_CARDS_SEED || []).slice();
    } catch(e) { _customCards = (CUSTOM_CARDS_SEED || []).slice(); }
  }
  function _ccSave() {
    try { localStorage.setItem(CUSTOM_CARDS_KEY, JSON.stringify(_customCards)); } catch(e) {}
    fetch('/save-custom-cards', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(_customCards)}).catch(function(){});
  }
  function _ccGenId() { return 'cc-' + Date.now() + '-' + Math.floor(Math.random()*9999); }

  function _ccExtract(obj, path) {
    if (!path) return obj;
    var p = path.replace(/^\$\.?/, '').replace(/^\./, '');
    if (!p) return obj;
    try {
      var parts = p.split(/[.\[\]]+/).filter(Boolean);
      var cur = obj;
      for (var i = 0; i < parts.length; i++) {
        if (cur === null || cur === undefined) return undefined;
        cur = cur[parts[i]];
      }
      return cur;
    } catch(e) { return undefined; }
  }

  function _ccThreshEval(value, op, thresh) {
    var v = String(value === null || value === undefined ? '' : value);
    var n = parseFloat(v);
    if (op === 'eq')       return v.toLowerCase() === (thresh||'').toLowerCase();
    if (op === 'neq')      return v.toLowerCase() !== (thresh||'').toLowerCase();
    if (op === 'contains') return v.toLowerCase().indexOf((thresh||'').toLowerCase()) !== -1;
    if (op === 'gt')       return !isNaN(n) && n >  parseFloat(thresh);
    if (op === 'lt')       return !isNaN(n) && n <  parseFloat(thresh);
    if (op === 'gte')      return !isNaN(n) && n >= parseFloat(thresh);
    if (op === 'lte')      return !isNaN(n) && n <= parseFloat(thresh);
    if (op === 'always')   return true;
    return false;
  }
  function _ccComputeState(value, thresholds) {
    if (!thresholds) return 'ok';
    var t = thresholds;
    if (t.red    && t.red.op    && t.red.op    !== 'never' && _ccThreshEval(value, t.red.op,    t.red.value    || '')) return 'crit';
    if (t.yellow && t.yellow.op && t.yellow.op !== 'never' && _ccThreshEval(value, t.yellow.op, t.yellow.value || '')) return 'warn';
    if (t.green  && t.green.op  && _ccThreshEval(value, t.green.op, t.green.value || '')) return 'ok';
    return 'ok';
  }

  function _ccSparkline(values, state) {
    if (!values || values.length < 2) return '<div class="spark-empty">No history yet</div>';
    var nums = values.map(Number).filter(function(v) { return !isNaN(v); });
    if (!nums.length) return '<div class="spark-empty">No numeric data</div>';
    var w=200, h=34, mn=Math.min.apply(null,nums), mx=Math.max.apply(null,nums), rng=mx-mn||1;
    var step = w / Math.max(nums.length-1,1);
    var pts = nums.map(function(v,i) {
      return (i*step).toFixed(1)+','+(h-((v-mn)/rng*(h-6)+3)).toFixed(1);
    });
    var cls = state==='warn'?'sp-warn':state==='crit'?'sp-crit':'';
    return '<svg class="spark '+cls+'" viewBox="0 0 '+w+' '+h+'">'
      +'<polyline class="spark-area" points="0,'+h+' '+pts.join(' ')+' '+w+','+h+'"/>'
      +'<polyline class="spark-line" points="'+pts.join(' ')+'"/>'
      +'<circle class="spark-dot" cx="'+pts[pts.length-1].split(',')[0]+'" cy="'+pts[pts.length-1].split(',')[1]+'" r="3"/>'
      +'</svg>';
  }
  var _ccHistKey = 'noc-cc-hist';
  function _ccLoadHist() { try { return JSON.parse(localStorage.getItem(_ccHistKey)||'{}'); } catch(e) { return {}; } }
  function _ccPushHist(id, val) {
    var h=_ccLoadHist(); if (!h[id]) h[id]=[];
    h[id].push(parseFloat(val)||0);
    if (h[id].length>48) h[id]=h[id].slice(-48);
    try { localStorage.setItem(_ccHistKey, JSON.stringify(h)); } catch(e) {}
  }

  function _ccRenderCard(el, cfg, data, errorMsg) {
    var state='degraded', bodyHtml='';
    var fields=cfg.fields||[], layout=cfg.layout||'keyvalue', thresholds=cfg.thresholds||null;
    if (errorMsg) {
      bodyHtml='<div class="custom-card-loading">Error: '+errorMsg.substring(0,80)+'</div>';
      state='error';
    } else if (data) {
      var fvals = fields.map(function(f) {
        var val = _ccExtract(data, f.path);
        if (val===null||val===undefined) val='\u2014';
        else if (typeof val==='object') val=JSON.stringify(val);
        else val=String(val);
        return {label:f.label||f.path, value:val, unit:f.unit||''};
      });
      var tIdx = (thresholds&&thresholds.field_index!=null)?parseInt(thresholds.field_index):0;
      var tVal = fvals[tIdx] ? fvals[tIdx].value : '';
      state = _ccComputeState(tVal, thresholds);
      if (layout==='graph') _ccPushHist(cfg.id, tVal);

      if (layout==='bignumber') {
        if (fvals.length) {
          var p=fvals[0], sc=state==='crit'?' m-crit':state==='warn'?' m-warn':'';
          bodyHtml='<div class="metric'+sc+'"><div class="m-v">'+p.value
            +(p.unit?'<span style="font-size:11px;color:var(--muted);margin-left:2px">'+p.unit+'</span>':'')
            +'</div><div class="m-l">'+p.label+'</div></div>';
          for (var i=1;i<fvals.length;i++) {
            var f2=fvals[i];
            bodyHtml+='<div class="metric"><div class="m-v" style="font-size:14px">'+f2.value
              +(f2.unit?'<span style="font-size:10px;color:var(--muted);margin-left:2px">'+f2.unit+'</span>':'')
              +'</div><div class="m-l">'+f2.label+'</div></div>';
          }
        } else { bodyHtml='<div class="custom-card-loading">No fields defined</div>'; }

      } else if (layout==='graph') {
        var hist=_ccLoadHist(), series=hist[cfg.id]||[];
        var spk=_ccSparkline(series,state);
        if (fvals.length) {
          var p0=fvals[0], sc0=state==='crit'?' m-crit':state==='warn'?' m-warn':'';
          bodyHtml='<div style="width:100%"><div class="trend">'+spk+'</div>'
            +'<div class="metric'+sc0+'" style="margin-top:6px"><div class="m-v">'+p0.value
            +(p0.unit?'<span style="font-size:11px;color:var(--muted);margin-left:2px">'+p0.unit+'</span>':'')
            +'</div><div class="m-l">'+p0.label+'</div></div></div>';
        } else { bodyHtml=spk; }

      } else {
        bodyHtml='<div class="kv-rows">'
          +fvals.map(function(fv) {
            return '<div class="kv-row"><span class="kv-lbl">'+fv.label+'</span>'
              +'<span class="kv-val">'+fv.value
              +(fv.unit?' <span style="font-size:10px;color:var(--muted)">'+fv.unit+'</span>':'')
              +'</span></div>';
          }).join('')+'</div>';
      }
    } else {
      bodyHtml='<div class="custom-card-loading">Loading\u2026</div>';
    }
    var cb=el.querySelector('.card-b');
    if (cb) cb.innerHTML=bodyHtml;
    ['s-ok','s-warn','s-crit','s-degraded','s-error'].forEach(function(c){el.classList.remove(c);});
    el.classList.add('s-'+state);
    el.setAttribute('data-state',state);
  }

  function _ccFetch(el, cfg) {
    if (!cfg.url) { _ccRenderCard(el,cfg,null,'No URL configured'); return; }
    var payload={
      url:cfg.url, auth_type:cfg.auth_type||'none', auth_value:cfg.auth_value||'',
      auth_key_header:cfg.auth_key_header||'X-API-Key',
      auth_user:cfg.auth_user||'', auth_pass:cfg.auth_pass||'',
      oauth_token_url:cfg.oauth_token_url||'', oauth_client_id:cfg.oauth_client_id||'',
      oauth_client_secret:cfg.oauth_client_secret||'', oauth_scope:cfg.oauth_scope||''
    };
    fetch('/api/fetch-custom',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
    .then(function(r){return r.json();})
    .then(function(d){
      if (d.ok) { _ccRenderCard(el,cfg,d.json||{__raw:d.raw},null); }
      else { _ccRenderCard(el,cfg,null,d.error||'Fetch failed'); }
    })
    .catch(function(e){ _ccRenderCard(el,cfg,null,e.message); });
  }
  function _ccStartFetch(el,cfg) {
    _ccFetch(el,cfg);
    if (_customFetchTimers[cfg.id]) clearInterval(_customFetchTimers[cfg.id]);
    _customFetchTimers[cfg.id]=setInterval(function(){_ccFetch(el,cfg);},60000);
  }

  function _ccCreateEl(cfg) {
    var el=document.createElement('div');
    var sizeClass=cfg.size?' '+cfg.size:'';
    el.className='card s-degraded'+sizeClass;
    el.setAttribute('data-title',cfg.title||'Custom Card');
    el.setAttribute('data-state','degraded');
    el.setAttribute('data-custom-card','true');
    el.setAttribute('data-card-id',cfg.id);
    el.style.cursor='pointer';
    el.addEventListener('click',function(){ if(!document.body.classList.contains('edit-mode')) focusCard(el); });
    el.innerHTML='<div class="card-h"><span class="dot"></span><h3>'+(cfg.title||'Custom Card')+'</h3></div>'
      +'<div class="card-b"><div class="custom-card-loading">Loading\u2026</div></div>';
    return el;
  }

  function _ccAddToSection(cfg, sectionTitle) {
    var targetRow=null;
    if (sectionTitle) {
      document.querySelectorAll('.section-label').forEach(function(lbl) {
        var t=(lbl.querySelector('.sec-title')||lbl).textContent.trim();
        if (t===sectionTitle) { var el=lbl.nextElementSibling; while(el&&el.classList.contains('row')){targetRow=el;el=el.nextElementSibling;} }
      });
    }
    if (!targetRow) { var rows=document.querySelectorAll('.row'); if(rows.length) targetRow=rows[rows.length-1]; }
    if (!targetRow) { addSection('Custom'); var all=document.querySelectorAll('.row'); targetRow=all[all.length-1]; }
    var cardEl=_ccCreateEl(cfg);
    targetRow.appendChild(cardEl);
    if (document.body.classList.contains('edit-mode')) _ccInjectEditBtns(cardEl);
    _ccStartFetch(cardEl,cfg);
    return cardEl;
  }

  function _ccInjectEditBtns(card) {
    if (!card.getAttribute('data-custom-card')) return;
    if (!card.querySelector('.card-edit-btn')) {
      var eb=document.createElement('button');
      eb.className='card-edit-btn'; eb.title='Edit card config'; eb.innerHTML='&#9998;';
      eb.addEventListener('click',function(e){
        e.stopPropagation();
        var id=card.getAttribute('data-card-id');
        var cfg=_customCards.find(function(c){return c.id===id;});
        if(cfg) openCustomCardBuilder(cfg);
      });
      card.appendChild(eb);
    }
    if (!card.querySelector('.card-rm-btn')) {
      var rm=document.createElement('button'); rm.className='card-rm-btn'; rm.title='Remove card'; rm.textContent='\u2715';
      rm.addEventListener('click',function(e){
        e.stopPropagation();
        if(!confirm('Remove this card? Config will also be deleted.')) return;
        var id=card.getAttribute('data-card-id');
        _customCards=_customCards.filter(function(c){return c.id!==id;});
        _ccSave();
        if(_customFetchTimers[id]){clearInterval(_customFetchTimers[id]);delete _customFetchTimers[id];}
        card.remove(); persistLayout();
      });
      card.appendChild(rm);
    }
    if (!card.querySelector('.card-resize-btn')) {
      var rs=document.createElement('button'); rs.className='card-resize-btn'; rs.title='Cycle size'; rs.textContent='\u2922';
      rs.addEventListener('click',function(e){
        e.stopPropagation();
        var sizes=['','card-wide','card-full','card-half'];
        var cur=sizes.find(function(s){return s&&card.classList.contains(s);})||'';
        var nxt=sizes[(sizes.indexOf(cur)+1)%sizes.length];
        sizes.forEach(function(s){if(s)card.classList.remove(s);}); if(nxt) card.classList.add(nxt);
        var id=card.getAttribute('data-card-id');
        var cfg=_customCards.find(function(c){return c.id===id;});
        if(cfg){cfg.size=nxt;_ccSave();}
        persistLayout();
      });
      card.appendChild(rs);
    }
  }

  function _ccRestore() {
    _ccLoad();
    if (!_customCards.length) return;
    _customCards.forEach(function(cfg) {
      if (document.querySelector('[data-card-id="'+cfg.id+'"]')) return;
      _ccAddToSection(cfg, cfg.section||null);
    });
  }

  /* ── Builder helpers ── */
  function _cbOpsHtml(sel) {
    var ops=[['always','Always'],['never','Never'],['eq','= Equals'],['neq','\u2260 Not Equals'],
             ['contains','Contains'],['gt','> Greater Than'],['lt','< Less Than'],
             ['gte','\u2265 ≥ Equals'],['lte','\u2264 ≤ Equals']];
    return ops.map(function(o){
      return '<option value="'+o[0]+'"'+(sel===o[0]?' selected':'')+'>'+o[1]+'</option>';
    }).join('');
  }

  function _cbAuthHtml(authType, cfg) {
    var c=cfg||{};
    if (authType==='bearer') {
      return '<div class="cb-auth-fields"><div class="cb-field span2"><label>Bearer Token</label>'
        +'<input type="password" id="cb-auth-bearer" placeholder="your-token" value="'+(c.auth_value||'')+'"></div></div>';
    }
    if (authType==='apikey') {
      return '<div class="cb-auth-fields">'
        +'<div class="cb-field"><label>Header Name</label><input type="text" id="cb-auth-key-hdr" placeholder="X-API-Key" value="'+(c.auth_key_header||'X-API-Key')+'"></div>'
        +'<div class="cb-field"><label>API Key Value</label><input type="password" id="cb-auth-key-val" placeholder="your-api-key" value="'+(c.auth_value||'')+'"></div></div>';
    }
    if (authType==='basic') {
      return '<div class="cb-auth-fields">'
        +'<div class="cb-field"><label>Username</label><input type="text" id="cb-auth-user" placeholder="username" value="'+(c.auth_user||'')+'"></div>'
        +'<div class="cb-field"><label>Password</label><input type="password" id="cb-auth-pass" placeholder="password" value="'+(c.auth_pass||'')+'"></div></div>';
    }
    if (authType==='oauth') {
      return '<div class="cb-auth-fields">'
        +'<div class="cb-field span2"><label>Token URL</label><input type="text" id="cb-oauth-url" placeholder="https://auth.example.com/token" value="'+(c.oauth_token_url||'')+'"></div>'
        +'<div class="cb-field"><label>Client ID</label><input type="text" id="cb-oauth-id" value="'+(c.oauth_client_id||'')+'"></div>'
        +'<div class="cb-field"><label>Client Secret</label><input type="password" id="cb-oauth-secret" value="'+(c.oauth_client_secret||'')+'"></div>'
        +'<div class="cb-field span2"><label>Scope (optional)</label><input type="text" id="cb-oauth-scope" placeholder="read:all" value="'+(c.oauth_scope||'')+'"></div></div>';
    }
    return '';
  }

  function _cbFieldRowHtml(f) {
    return '<div class="cb-field-row">'
      +'<input type="text" class="cb-fl" placeholder="Label (e.g. Status)" value="'+(f.label||'')+'">'
      +'<input type="text" class="cb-fp" placeholder=".status  or  data.health" value="'+(f.path||'')+'">'
      +'<button class="cb-rm" type="button" title="Remove">\u00d7</button></div>';
  }

  function _cbWireFieldBtns() {
    var list=document.getElementById('cb-fields-list'); if(!list) return;
    list.querySelectorAll('.cb-rm').forEach(function(btn){
      btn.onclick=function(){
        if(list.querySelectorAll('.cb-field-row').length<=1) return;
        btn.closest('.cb-field-row').remove(); _cbUpdateThreshSel();
      };
    });
    var addBtn=document.getElementById('cb-add-field-btn');
    if(addBtn) addBtn.onclick=function(){
      var row=document.createElement('div'); row.className='cb-field-row';
      row.innerHTML='<input type="text" class="cb-fl" placeholder="Label">'
        +'<input type="text" class="cb-fp" placeholder=".field_name">'
        +'<button class="cb-rm" type="button">\u00d7</button>';
      list.appendChild(row); _cbWireFieldBtns(); _cbUpdateThreshSel();
    };
  }

  function _cbUpdateThreshSel() {
    var sel=document.getElementById('cb-thresh-field'); if(!sel) return;
    var rows=document.querySelectorAll('#cb-fields-list .cb-field-row');
    sel.innerHTML=Array.from(rows).map(function(row,i){
      var lbl=(row.querySelector('.cb-fl')||{}).value||('Field '+(i+1));
      return '<option value="'+i+'">Field '+(i+1)+': '+lbl+'</option>';
    }).join('');
  }

  window._cbAuthChange=function(val){
    var c=document.getElementById('cb-auth-fields-container');
    if(c) c.innerHTML=_cbAuthHtml(val,{});
  };

  window.openCustomCardBuilder=function(existingCfg){
    _builderEditId=existingCfg?existingCfg.id:null;
    var ov=document.getElementById('custom-builder-overlay'); if(!ov) return;
    var cfg=existingCfg||{};
    var fields=cfg.fields&&cfg.fields.length?cfg.fields:[{label:'Value',path:'.status'}];
    var t=cfg.thresholds||{field_index:0,green:{op:'always',value:''},yellow:{op:'never',value:''},red:{op:'never',value:''}};
    var authType=cfg.auth_type||'none';
    var secs=Array.from(document.querySelectorAll('.section-label')).map(function(l){return (l.querySelector('.sec-title')||l).textContent.trim();});
    var secOpts=secs.map(function(s){return '<option value="'+s+'"'+(cfg.section===s?' selected':'')+'>'+s+'</option>';}).join('');

    document.getElementById('cb-form').innerHTML=''
      +'<div class="cb-section-hdr">Card Info</div>'
      +'<div class="cb-grid">'
        +'<div class="cb-field span2"><label>Card Title</label><input type="text" id="cb-title" placeholder="My Service" value="'+(cfg.title||'')+'" autocomplete="off"></div>'
        +'<div class="cb-field span2"><label>Data Source URL</label><input type="text" id="cb-url" placeholder="http://host:port/api/status" value="'+(cfg.url||'')+'" autocomplete="off"></div>'
      +'</div>'
      +'<div class="cb-section-hdr">Authentication</div>'
      +'<div class="cb-grid"><div class="cb-field"><label>Auth Method</label>'
        +'<select id="cb-auth-type" onchange="_cbAuthChange(this.value)">'
          +'<option value="none"'   +(authType==='none'  ?' selected':'')+'>None</option>'
          +'<option value="bearer"' +(authType==='bearer'?' selected':'')+'>Bearer Token</option>'
          +'<option value="apikey"' +(authType==='apikey'?' selected':'')+'>API Key Header</option>'
          +'<option value="basic"'  +(authType==='basic' ?' selected':'')+'>Username + Password</option>'
          +'<option value="oauth"'  +(authType==='oauth' ?' selected':'')+'>OAuth 2.0 Client Credentials</option>'
        +'</select></div></div>'
      +'<div id="cb-auth-fields-container">'+_cbAuthHtml(authType,cfg)+'</div>'
      +'<div class="cb-section-hdr">Fields to Extract</div>'
      +'<div class="cb-hint">Dot-notation or JSONPath: <code>.status</code> &nbsp; <code>data.health</code> &nbsp; <code>$.items[0].count</code><br>'
        +'The field path is extracted from the JSON response. Leave blank to use the whole response.</div>'
      +'<div id="cb-fields-list" class="cb-fields-list">'+fields.map(_cbFieldRowHtml).join('')+'</div>'
      +'<button class="cb-add-field-btn" id="cb-add-field-btn" type="button">+ Add Field</button>'
      +'<div class="cb-section-hdr">Display &amp; Placement</div>'
      +'<div class="cb-grid">'
        +'<div class="cb-field"><label>Layout</label>'
          +'<select id="cb-layout">'
            +'<option value="keyvalue"'  +((!cfg.layout||cfg.layout==='keyvalue')?' selected':'')+'>Key-Value Rows</option>'
            +'<option value="bignumber"' +(cfg.layout==='bignumber'?' selected':'')+'>Big Number</option>'
            +'<option value="graph"'     +(cfg.layout==='graph'?' selected':'')+'>Graph (Sparkline)</option>'
          +'</select></div>'
        +'<div class="cb-field"><label>Card Size</label>'
          +'<select id="cb-size">'
            +'<option value=""'         +(!cfg.size?' selected':'')+'>Default</option>'
            +'<option value="card-wide"'+(cfg.size==='card-wide'?' selected':'')+'>Wide (2 cols)</option>'
            +'<option value="card-half"'+(cfg.size==='card-half'?' selected':'')+'>Half Width</option>'
            +'<option value="card-full"'+(cfg.size==='card-full'?' selected':'')+'>Full Width</option>'
          +'</select></div>'
        +(secOpts?'<div class="cb-field"><label>Add to Section</label><select id="cb-section">'+secOpts+'</select></div>':'')
      +'</div>'
      +'<div class="cb-section-hdr">Status Thresholds</div>'
      +'<div class="cb-hint">Choose which field determines the card status indicator.</div>'
      +'<div class="cb-grid"><div class="cb-field"><label>Status Field</label>'
        +'<select id="cb-thresh-field">'+fields.map(function(f,i){
          return '<option value="'+i+'"'+(t.field_index===i?' selected':'')+'>Field '+(i+1)+': '+(f.label||f.path)+'</option>';
        }).join('')+'</select></div></div>'
      +'<div class="cb-thresh-grid">'
        +'<span class="cb-thresh-lbl g">\u25cf Green when</span>'
        +'<select id="cb-green-op">'+_cbOpsHtml(t.green&&t.green.op)+'</select>'
        +'<input type="text" id="cb-green-val" placeholder="value" value="'+(t.green&&t.green.value||'')+'">'
        +'<span class="cb-thresh-lbl y">\u25cf Yellow when</span>'
        +'<select id="cb-yellow-op">'+_cbOpsHtml(t.yellow&&t.yellow.op)+'</select>'
        +'<input type="text" id="cb-yellow-val" placeholder="value" value="'+(t.yellow&&t.yellow.value||'')+'">'
        +'<span class="cb-thresh-lbl r">\u25cf Red when</span>'
        +'<select id="cb-red-op">'+_cbOpsHtml(t.red&&t.red.op)+'</select>'
        +'<input type="text" id="cb-red-val" placeholder="value" value="'+(t.red&&t.red.value||'')+'">'
      +'</div>';

    var msgEl=document.getElementById('cb-save-msg'); if(msgEl) msgEl.textContent='';
    _cbWireFieldBtns();
    ov.classList.add('open'); document.body.style.overflow='hidden';
    setTimeout(function(){var el=document.getElementById('cb-title');if(el)el.focus();},60);
  };

  window.closeCustomCardBuilder=function(){
    var ov=document.getElementById('custom-builder-overlay');
    if(ov) ov.classList.remove('open');
    document.body.style.overflow=''; _builderEditId=null;
  };

  window.testCustomCardFetch=function(){
    var msg=document.getElementById('cb-save-msg');
    var url=(document.getElementById('cb-url')||{}).value||'';
    if(!url){if(msg){msg.className='cb-msg err';msg.textContent='Enter a URL first.';}return;}
    if(msg){msg.className='cb-msg';msg.textContent='\u29d9 Testing\u2026';}
    var authType=(document.getElementById('cb-auth-type')||{}).value||'none';
    var p={url:url,auth_type:authType,auth_value:'',auth_key_header:'X-API-Key',auth_user:'',auth_pass:''};
    if(authType==='bearer') p.auth_value=(document.getElementById('cb-auth-bearer')||{}).value||'';
    else if(authType==='apikey'){p.auth_key_header=(document.getElementById('cb-auth-key-hdr')||{}).value||'X-API-Key';p.auth_value=(document.getElementById('cb-auth-key-val')||{}).value||'';}
    else if(authType==='basic'){p.auth_user=(document.getElementById('cb-auth-user')||{}).value||'';p.auth_pass=(document.getElementById('cb-auth-pass')||{}).value||'';}
    fetch('/api/fetch-custom',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){
        var prev=typeof d.json==='object'?JSON.stringify(d.json).substring(0,120):(d.raw||'').substring(0,120);
        if(msg){msg.className='cb-msg ok';msg.textContent='\u2713 OK \u2014 '+prev;}
      } else {if(msg){msg.className='cb-msg err';msg.textContent='\u2715 '+(d.error||'Failed');}}
    })
    .catch(function(e){if(msg){msg.className='cb-msg err';msg.textContent='\u2715 '+e.message;}});
  };

  window.saveCustomCard=function(){
    var msg=document.getElementById('cb-save-msg');
    function _v(id){var el=document.getElementById(id);return el?el.value:'';}
    var title=_v('cb-title').trim(), url=_v('cb-url').trim();
    if(!title){if(msg){msg.className='cb-msg err';msg.textContent='Title is required.';}return;}
    if(!url){if(msg){msg.className='cb-msg err';msg.textContent='URL is required.';}return;}
    var authType=_v('cb-auth-type')||'none';
    var aval='',akhdr='X-API-Key',auser='',apass='',ourl='',oid='',osec='',oscp='';
    if(authType==='bearer') aval=_v('cb-auth-bearer');
    else if(authType==='apikey'){akhdr=_v('cb-auth-key-hdr')||'X-API-Key';aval=_v('cb-auth-key-val');}
    else if(authType==='basic'){auser=_v('cb-auth-user');apass=_v('cb-auth-pass');}
    else if(authType==='oauth'){ourl=_v('cb-oauth-url');oid=_v('cb-oauth-id');osec=_v('cb-oauth-secret');oscp=_v('cb-oauth-scope');}
    var fieldRows=document.querySelectorAll('#cb-fields-list .cb-field-row');
    var fields=Array.from(fieldRows).map(function(row){
      var lbl=(row.querySelector('.cb-fl')||{}).value||'';
      var path=(row.querySelector('.cb-fp')||{}).value||'';
      return {label:lbl||path,path:path};
    }).filter(function(f){return f.path;});
    if(!fields.length) fields=[{label:'Value',path:'.status'}];
    var layout=_v('cb-layout')||'keyvalue', size=_v('cb-size')||'', section=_v('cb-section')||'';
    var tfi=parseInt(_v('cb-thresh-field'))||0;
    var thresholds={field_index:tfi,
      green:{op:_v('cb-green-op')||'always',value:_v('cb-green-val')},
      yellow:{op:_v('cb-yellow-op')||'never',value:_v('cb-yellow-val')},
      red:{op:_v('cb-red-op')||'never',value:_v('cb-red-val')}};
    var cfg={
      id:_builderEditId||_ccGenId(),title:title,url:url,
      auth_type:authType,auth_value:aval,auth_key_header:akhdr,auth_user:auser,auth_pass:apass,
      oauth_token_url:ourl,oauth_client_id:oid,oauth_client_secret:osec,oauth_scope:oscp,
      fields:fields,layout:layout,size:size,section:section,thresholds:thresholds
    };
    if(_builderEditId){
      var idx=_customCards.findIndex(function(c){return c.id===_builderEditId;});
      if(idx!==-1) _customCards[idx]=cfg;
      var el=document.querySelector('[data-card-id="'+_builderEditId+'"]');
      if(el){
        var h3=el.querySelector('h3'); if(h3) h3.textContent=cfg.title;
        el.setAttribute('data-title',cfg.title);
        ['card-wide','card-full','card-half'].forEach(function(s){el.classList.remove(s);});
        if(cfg.size) el.classList.add(cfg.size);
        _ccFetch(el,cfg);
      }
    } else {
      _customCards.push(cfg);
      _ccAddToSection(cfg,section);
    }
    _ccSave();
    if(msg){msg.className='cb-msg ok';msg.textContent='\u2713 Card saved';}
    setTimeout(closeCustomCardBuilder,700);
  };

  /* Patch toggleEditMode to wire edit-pencil + CARD btn visibility */
  var _origToggleEM=window.toggleEditMode;
  window.toggleEditMode=function(){
    var ret=_origToggleEM.apply(this, arguments);
    var isEdit=document.body.classList.contains('edit-mode');
    var addBtn=document.getElementById('add-custom-card-btn');
    if(addBtn) addBtn.style.display='none';
    if(isEdit){
      document.querySelectorAll('[data-custom-card="true"]').forEach(function(c){_ccInjectEditBtns(c);});
    } else {
      document.querySelectorAll('.card-edit-btn').forEach(function(b){b.remove();});
    }
  };
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){
      var ov=document.getElementById('custom-builder-overlay');
      if(ov&&ov.classList.contains('open')){closeCustomCardBuilder();return;}
    }
  });
  _ccRestore();

  /* ── Built-in Card Customization System ── */
  var BUILTIN_CARD_CONFIG_SEED = __BCC_SEED__;
  var BUILTIN_CARD_CONFIG_KEY = 'noc-builtin-card-configs';
  var _builtinCardConfigs = {};
  var _builtinEditCard = null;

  function _bccLoad() {
    try {
      var stored = JSON.parse(localStorage.getItem(BUILTIN_CARD_CONFIG_KEY) || '{}');
      _builtinCardConfigs = Object.assign({}, BUILTIN_CARD_CONFIG_SEED || {}, stored || {});
    } catch(e) { _builtinCardConfigs = Object.assign({}, BUILTIN_CARD_CONFIG_SEED || {}); }
  }
  function _bccSave() {
    try { localStorage.setItem(BUILTIN_CARD_CONFIG_KEY, JSON.stringify(_builtinCardConfigs)); } catch(e) {}
    fetch('/save-builtin-card-configs', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(_builtinCardConfigs)}).catch(function(){});
  }
  function _bccCardId(card) {
    if (!card) return '';
    var id = card.getAttribute('data-card-id');
    if (id) return id;
    var h3 = card.querySelector('h3');
    id = (h3 ? h3.textContent : 'card').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');
    card.setAttribute('data-card-id', id);
    return id;
  }
  function _bccTitle(card) { var h3=card.querySelector('h3'); return h3 ? h3.textContent.trim() : _bccCardId(card); }
  function _bccRows(card) {
    var selectors = ['.metric','.kv-row','.qrow','.alerts li','.cert','.hbar-row','.panelbox > div','.card-b > div'];
    var seen = new Set(), rows = [];
    selectors.forEach(function(sel){
      card.querySelectorAll(sel).forEach(function(el){
        if (seen.has(el) || el.closest('.builtin-card-config-overlay')) return;
        if (el.classList.contains('card-h') || el.classList.contains('card-b')) return;
        var text = el.textContent.trim().replace(/\s+/g,' ');
        if (!text || text.length < 2) return;
        seen.add(el);
        var id = el.getAttribute('data-bcc-row-id');
        if (!id) { id = 'row-' + rows.length + '-' + text.toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,32); el.setAttribute('data-bcc-row-id', id); }
        rows.push({id:id, label:text.slice(0,90), el:el});
      });
    });
    return rows;
  }
  function _bccDefaultCfg(card) {
    var rows = _bccRows(card);
    return {title:_bccTitle(card), size:'', warn:'75', crit:'90', rows:rows.map(function(r,i){return {id:r.id,label:r.label,visible:true,order:i};})};
  }
  function _bccApplyCard(card) {
    if (!card || card.getAttribute('data-custom-card') === 'true') return;
    var id = _bccCardId(card), cfg = _builtinCardConfigs[id];
    if (!cfg) return;
    var h3 = card.querySelector('h3');
    if (h3 && cfg.title) { h3.textContent = cfg.title; card.setAttribute('data-title', cfg.title); }
    ['card-wide','card-full','card-half'].forEach(function(s){card.classList.remove(s);});
    if (cfg.size) card.classList.add(cfg.size);
    var rows = _bccRows(card), rowMap = {};
    rows.forEach(function(r){ rowMap[r.id] = r; r.el.classList.remove('builtin-hidden-field'); });
    (cfg.rows || []).forEach(function(rc){ if (rowMap[rc.id] && rc.visible === false) rowMap[rc.id].el.classList.add('builtin-hidden-field'); });
    var ordered = (cfg.rows || []).slice().sort(function(a,b){return (a.order||0)-(b.order||0);});
    ordered.forEach(function(rc){
      var r = rowMap[rc.id]; if (!r || !r.el.parentNode) return;
      r.el.parentNode.appendChild(r.el);
    });
    var nums = card.textContent.match(/\d+(?:\.\d+)?\s*%/g) || card.textContent.match(/\d+(?:\.\d+)?/g) || [];
    if (nums.length) {
      var n = parseFloat(nums[0]); var warn = parseFloat(cfg.warn || '75'); var crit = parseFloat(cfg.crit || '90');
      ['s-ok','s-warn','s-crit','s-degraded','s-error'].forEach(function(c){card.classList.remove(c);});
      var st = n >= crit ? 'crit' : n >= warn ? 'warn' : 'ok';
      card.classList.add('s-' + st); card.setAttribute('data-state', st);
    }
  }
  function _bccInjectGear(card) {
    if (!card || card.getAttribute('data-custom-card') === 'true') return;
    _bccCardId(card);
    if (card.querySelector('.card-gear-btn')) return;
    var gb = document.createElement('button');
    gb.className = 'card-gear-btn'; gb.title = 'Card settings'; gb.innerHTML = '&#9881;';
    gb.addEventListener('click', function(e){ e.stopPropagation(); openBuiltinCardConfig(card); });
    card.appendChild(gb);
  }
  function _bccInitCards() {
    _bccLoad();
    document.querySelectorAll('.card').forEach(function(card){ _bccInjectGear(card); _bccApplyCard(card); });
  }
  function _bccRowsHtml(rows, cfgRows) {
    var byId = {}; (cfgRows || []).forEach(function(r){ byId[r.id]=r; });
    return rows.map(function(r,i){
      var c = byId[r.id] || {visible:true, order:i};
      return '<div class="bcc-row" data-row-id="'+r.id+'">'
        +'<input type="checkbox" class="bcc-visible" '+(c.visible===false?'':'checked')+'>'
        +'<div class="bcc-row-name" title="'+r.label.replace(/"/g,'&quot;')+'">'+r.label+'</div>'
        +'<button type="button" class="bcc-up" title="Move up">&#8593;</button>'
        +'<button type="button" class="bcc-down" title="Move down">&#8595;</button></div>';
    }).join('') || '<div class="cb-hint">No individual fields detected. Title, thresholds, and size still apply.</div>';
  }
  window.openBuiltinCardConfig = function(card) {
    _builtinEditCard = card;
    var id=_bccCardId(card), defaults=_bccDefaultCfg(card), cfg=Object.assign({}, defaults, _builtinCardConfigs[id] || {});
    var rows=_bccRows(card);
    var form=document.getElementById('bcc-form'), ov=document.getElementById('builtin-config-overlay'); if(!form||!ov) return;
    form.innerHTML = '<div class="bcc-section-hdr">Card Identity</div><div class="bcc-grid">'
      +'<div class="bcc-field"><label>Card Title</label><input id="bcc-title" type="text" value="'+(cfg.title||defaults.title).replace(/"/g,'&quot;')+'"></div>'
      +'<div class="bcc-field"><label>Card Size</label><select id="bcc-size">'
      +'<option value="" '+(!cfg.size?'selected':'')+'>Default</option><option value="card-wide" '+(cfg.size==='card-wide'?'selected':'')+'>Wide</option><option value="card-half" '+(cfg.size==='card-half'?'selected':'')+'>Half Width</option><option value="card-full" '+(cfg.size==='card-full'?'selected':'')+'>Full Width</option></select></div>'
      +'<div class="bcc-field"><label>Warning Threshold</label><input id="bcc-warn" type="number" value="'+(cfg.warn||'75')+'"></div>'
      +'<div class="bcc-field"><label>Critical Threshold</label><input id="bcc-crit" type="number" value="'+(cfg.crit||'90')+'"></div></div>'
      +'<div class="bcc-section-hdr">Visible Fields / Row Order</div><div class="cb-hint">Toggle rows, then use arrows to reorder what the card displays.</div>'
      +'<div id="bcc-rows" class="bcc-rows">'+_bccRowsHtml(rows, cfg.rows)+'</div>';
    form.querySelectorAll('.bcc-up,.bcc-down').forEach(function(btn){btn.onclick=function(){var row=btn.closest('.bcc-row'); if(!row)return; if(btn.classList.contains('bcc-up')&&row.previousElementSibling) row.parentNode.insertBefore(row,row.previousElementSibling); if(btn.classList.contains('bcc-down')&&row.nextElementSibling) row.parentNode.insertBefore(row.nextElementSibling,row);};});
    var msg=document.getElementById('bcc-save-msg'); if(msg) msg.textContent='';
    ov.classList.add('open'); document.body.style.overflow='hidden';
  };
  window.closeBuiltinCardConfig = function(){ var ov=document.getElementById('builtin-config-overlay'); if(ov) ov.classList.remove('open'); document.body.style.overflow=''; _builtinEditCard=null; };
  window.resetBuiltinCardConfig = function(){ if(!_builtinEditCard)return; var id=_bccCardId(_builtinEditCard); delete _builtinCardConfigs[id]; _bccSave(); location.reload(); };
  window.saveBuiltinCardConfig = function(){
    if(!_builtinEditCard) return; var id=_bccCardId(_builtinEditCard);
    var rows = Array.from(document.querySelectorAll('#bcc-rows .bcc-row')).map(function(row,i){ return {id:row.dataset.rowId, label:(row.querySelector('.bcc-row-name')||{}).textContent||'', visible:!!(row.querySelector('.bcc-visible')||{}).checked, order:i}; });
    _builtinCardConfigs[id] = {title:(document.getElementById('bcc-title')||{}).value||_bccTitle(_builtinEditCard), size:(document.getElementById('bcc-size')||{}).value||'', warn:(document.getElementById('bcc-warn')||{}).value||'75', crit:(document.getElementById('bcc-crit')||{}).value||'90', rows:rows};
    _bccApplyCard(_builtinEditCard); _bccSave(); persistLayout();
    var msg=document.getElementById('bcc-save-msg'); if(msg){msg.className='cb-msg ok';msg.textContent='\u2713 Card settings saved';}
    setTimeout(closeBuiltinCardConfig,650);
  };
  document.addEventListener('keydown',function(e){ if(e.key==='Escape'){ var ov=document.getElementById('builtin-config-overlay'); if(ov&&ov.classList.contains('open')){closeBuiltinCardConfig();return;} } });
  _bccInitCards();

"""


INTEL_CSS = """
  .intel-panel,.intel-panel-scroll,.intel-card-body,.hs-breakdown{scrollbar-width:auto;scrollbar-color:var(--green) rgba(0,0,0,.32)}.intel-panel::-webkit-scrollbar,.intel-panel-scroll::-webkit-scrollbar,.intel-card-body::-webkit-scrollbar,.hs-breakdown::-webkit-scrollbar{width:10px;height:10px}.intel-panel::-webkit-scrollbar-track,.intel-panel-scroll::-webkit-scrollbar-track,.intel-card-body::-webkit-scrollbar-track,.hs-breakdown::-webkit-scrollbar-track{background:rgba(0,0,0,.32);border-left:1px solid var(--line)}.intel-panel::-webkit-scrollbar-thumb,.intel-panel-scroll::-webkit-scrollbar-thumb,.intel-card-body::-webkit-scrollbar-thumb,.hs-breakdown::-webkit-scrollbar-thumb{background:linear-gradient(180deg,var(--green),var(--green-dim));border-radius:999px;border:2px solid rgba(0,0,0,.32)}.intel-panel-scroll{overflow-y:scroll;scrollbar-gutter:stable;padding-right:10px}.intel-card-body{max-height:min(260px,34vh);overflow-y:auto;scrollbar-gutter:stable;padding-right:8px}.intel-health-card .intel-card-body{max-height:min(300px,38vh)}.hs-breakdown{max-height:190px;overflow-y:auto;padding-right:6px}.intel-card.closed .intel-card-body{display:none!important}
  .health-card-body{display:flex;gap:12px;align-items:center;width:100%;}.hs-donut-wrap{width:110px;flex:none}.hs-donut{width:110px;height:110px}.hs-track{fill:none;stroke:#162016;stroke-width:10}.hs-val{fill:none;stroke-width:10;stroke-linecap:round}.hs-ok .hs-val{stroke:var(--green)}.hs-warn .hs-val{stroke:var(--warn)}.hs-crit .hs-val{stroke:var(--crit)}.hs-pct{font-size:23px;font-weight:800;text-anchor:middle;fill:var(--txt)}.hs-breakdown{flex:1;min-width:0}.hs-row{display:flex;justify-content:space-between;gap:10px;padding:4px 0;border-bottom:1px dashed rgba(111,138,111,.18);font-size:11px}.hs-row span{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-transform:uppercase;letter-spacing:.04em}.hs-row b{color:var(--txt);white-space:nowrap}.q-ok{color:var(--green)!important}.q-warn{color:var(--warn)!important}.q-crit{color:var(--crit)!important}.intel-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.48);z-index:8500}.intel-overlay.open{display:block}.intel-panel{position:fixed;top:0;right:-520px;width:min(500px,94vw);height:100vh;background:linear-gradient(180deg,var(--panel),var(--bg));border-left:1px solid var(--line);z-index:8501;transition:right .26s ease;box-shadow:-10px 0 34px rgba(0,0,0,.65);display:flex;flex-direction:column;overflow-y:auto}.intel-panel.open{right:0}.intel-panel-hdr{display:flex;align-items:center;justify-content:space-between;padding:15px 18px;border-bottom:1px solid var(--line);color:var(--green);font-weight:800;letter-spacing:.12em;font-size:12px}.intel-panel-hdr button{background:none;border:1px solid var(--line);color:var(--muted);cursor:pointer;border-radius:3px;font-size:18px;line-height:1;padding:2px 8px}.intel-panel-scroll{overflow-y:auto;overflow-x:hidden;padding:12px;display:flex;flex-direction:column;gap:10px;min-height:0;flex:1}.intel-card{border:1px solid var(--line);border-radius:6px;background:rgba(0,0,0,.18);overflow:hidden}.intel-card.closed .intel-card-body{display:none}.intel-card.closed .intel-card-title b{font-size:0}.intel-card.closed .intel-card-title b:after{content:'+';font-size:16px}.intel-card-title{width:100%;display:flex;justify-content:space-between;align-items:center;background:rgba(0,255,65,.035);border:none;border-bottom:1px solid var(--line);color:var(--green-dim);cursor:pointer;padding:10px 12px;font-size:11px;letter-spacing:.12em;font-weight:700}.intel-card-body{padding:12px;max-height:32vh;overflow-y:auto;overflow-x:hidden}.intel-big-score{font-size:30px;font-weight:800;text-align:center;border:1px solid var(--line);border-radius:4px;padding:10px;margin-bottom:8px}.intel-dual-score{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px}.intel-dual-score span{border:1px solid var(--line);border-radius:4px;padding:8px;text-align:center;color:var(--muted);font-size:11px}.intel-dual-score b{display:block;font-size:22px}.intel-list-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;align-items:center;padding:6px 0;border-bottom:1px dashed rgba(111,138,111,.16);font-size:11px}.intel-list-row span{color:var(--txt);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.intel-list-row em{color:var(--muted);font-style:normal;font-size:10px}.intel-storage-row{margin:10px 0}.intel-storage-row div:first-child{display:flex;justify-content:space-between;gap:8px;font-size:11px;margin-bottom:4px}.intel-bar{height:8px;background:#0c140c;border:1px solid var(--line);border-radius:5px;overflow:hidden}.intel-bar span{display:block;height:100%;background:var(--green)}.intel-bar span.q-warn{background:var(--warn)}.intel-bar span.q-crit{background:var(--crit)}.intel-cert-flag{color:var(--crit);border:1px solid rgba(255,59,59,.35);background:rgba(255,59,59,.08);padding:8px 10px;border-radius:4px;font-size:11px;margin-bottom:8px}.intel-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);backdrop-filter:blur(4px);z-index:9100;align-items:center;justify-content:center}.intel-modal.open{display:flex}.intel-modal-box{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:24px;width:min(860px,94vw);max-height:86vh;overflow:auto;position:relative}.intel-tabs{display:flex;gap:8px;margin:0 0 14px}.intel-tabs button{background:none;border:1px solid var(--line);color:var(--muted);cursor:pointer;border-radius:3px;padding:5px 10px;font-size:10px;letter-spacing:.1em}.intel-tabs button.active{color:var(--green);border-color:var(--green);background:rgba(0,255,65,.07)}.intel-tab,.intel-range-pane{display:none}.intel-tab.active,.intel-range-pane.active{display:block}.hs-modal-score{font-size:42px;font-weight:800;text-align:center;margin-bottom:10px}.hs-line{height:180px;width:100%;border:1px solid var(--line);background:rgba(0,0,0,.18)}.hs-line polyline{fill:none;stroke:var(--green);stroke-width:2}.hs-incident{border-left:3px solid var(--line);background:rgba(0,0,0,.18);padding:8px 10px;font-size:11px;margin-bottom:8px}.hs-incident span{color:var(--muted);display:block;font-size:10px}.hs-incident b{color:var(--txt);margin-right:8px}.hs-incident em{color:var(--muted);font-style:normal}.hs-incident p{margin:4px 0 0;color:var(--txt)}@media(max-width:900px){.health-card-body{flex-direction:column;align-items:flex-start}.top-right{gap:8px;flex-wrap:wrap}}
  /* INTEL hybrid scrolling: panel scrolls, only Certificate Expiry scrolls internally. */
  .intel-panel,.intel-panel-scroll,.intel-card-body,.intel-cert-card .intel-card-body,.intel-modal-box,.settings-content,.settings-sidebar,.alert-panel,.reports-panel,.card-modal-box{scrollbar-width:thin;scrollbar-color:var(--green) rgba(0,0,0,.24)}
  .intel-panel::-webkit-scrollbar,.intel-panel-scroll::-webkit-scrollbar,.intel-card-body::-webkit-scrollbar,.intel-cert-card .intel-card-body::-webkit-scrollbar,.intel-modal-box::-webkit-scrollbar,.settings-content::-webkit-scrollbar,.settings-sidebar::-webkit-scrollbar,.alert-panel::-webkit-scrollbar,.reports-panel::-webkit-scrollbar,.card-modal-box::-webkit-scrollbar{width:6px;height:6px}
  .intel-panel::-webkit-scrollbar-track,.intel-panel-scroll::-webkit-scrollbar-track,.intel-card-body::-webkit-scrollbar-track,.intel-cert-card .intel-card-body::-webkit-scrollbar-track,.intel-modal-box::-webkit-scrollbar-track,.settings-content::-webkit-scrollbar-track,.settings-sidebar::-webkit-scrollbar-track,.alert-panel::-webkit-scrollbar-track,.reports-panel::-webkit-scrollbar-track,.card-modal-box::-webkit-scrollbar-track{background:rgba(0,0,0,.24)}
  .intel-panel::-webkit-scrollbar-thumb,.intel-panel-scroll::-webkit-scrollbar-thumb,.intel-card-body::-webkit-scrollbar-thumb,.intel-cert-card .intel-card-body::-webkit-scrollbar-thumb,.intel-modal-box::-webkit-scrollbar-thumb,.settings-content::-webkit-scrollbar-thumb,.settings-sidebar::-webkit-scrollbar-thumb,.alert-panel::-webkit-scrollbar-thumb,.reports-panel::-webkit-scrollbar-thumb,.card-modal-box::-webkit-scrollbar-thumb{background:var(--green);border-radius:999px;border:1px solid rgba(0,0,0,.35)}
  .intel-panel{overflow-y:auto!important;scrollbar-gutter:stable;height:100vh}
  .intel-panel-scroll{overflow:visible!important;display:flex;flex-direction:column;gap:10px;min-height:auto!important;flex:0 0 auto!important;padding:12px 16px 18px 12px!important}
  .intel-card{overflow:visible!important}
  .intel-card-body{max-height:none!important;overflow:visible!important;scrollbar-gutter:auto;padding-right:12px!important}
  .intel-health-card .intel-card-body,.intel-backup-card .intel-card-body,.intel-security-card .intel-card-body,.intel-storage-card .intel-card-body{max-height:none!important;overflow:visible!important}
  .intel-cert-card .intel-card-body{max-height:min(360px,42vh)!important;overflow-y:auto!important;overflow-x:hidden!important;scrollbar-gutter:stable;padding-right:8px!important}
  .hs-breakdown{max-height:none!important;overflow:visible!important;padding-right:0!important}

"""

INTEL_JS = """
  function _nocBackdropClick(e, overlay, panelSelector){
    if(!e||!overlay||e.target!==overlay) return false;
    if(e.clientX>=document.documentElement.clientWidth||e.clientY>=document.documentElement.clientHeight) return false;
    var p=panelSelector?document.querySelector(panelSelector):null;
    var path=e.composedPath?e.composedPath():[];
    if(p&&(p.contains(e.target)||path.indexOf(p)!==-1)) return false;
    return true;
  }
  window.toggleIntel=function(open){var ov=document.getElementById('intel-overlay'),p=document.getElementById('intel-panel'); if(!ov||!p)return; var show=(open===undefined)?!p.classList.contains('open'):!!open; ov.classList.toggle('open',show); p.classList.toggle('open',show);};
  window.intelOverlayClick=function(e){var ov=document.getElementById('intel-overlay'); if(_nocBackdropClick(e,ov,'#intel-panel'))toggleIntel(false);};
  window.openHealthModal=function(e){if(e)e.stopPropagation(); var m=document.getElementById('health-modal'); if(m)m.classList.add('open');};
  window.closeHealthModal=function(){var m=document.getElementById('health-modal'); if(m)m.classList.remove('open');};
  window.intelTab=function(e,id){var box=e.target.closest('.intel-modal-box'); Array.prototype.forEach.call(box.querySelectorAll('.intel-tabs:first-of-type button'),function(b){b.classList.remove('active')}); e.target.classList.add('active'); Array.prototype.forEach.call(box.querySelectorAll('.intel-tab'),function(p){p.classList.remove('active')}); var p=document.getElementById(id); if(p)p.classList.add('active');};
  window.intelRange=function(e,id){var parent=e.target.closest('#hs-trend'); Array.prototype.forEach.call(parent.querySelectorAll('.range button'),function(b){b.classList.remove('active')}); e.target.classList.add('active'); Array.prototype.forEach.call(parent.querySelectorAll('.intel-range-pane'),function(p){p.classList.remove('active')}); var p=document.getElementById(id); if(p)p.classList.add('active');};
  document.addEventListener('keydown',function(e){if(e.key==='Escape'){toggleIntel(false);closeHealthModal();}});
"""

PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{doc_title}</title>
<link rel="icon" id="noc-favicon" type="image/svg+xml" href="">
<style>
  :root {{
    --bg:#0a0e0a; --panel:#0f150f; --panel2:#121a12; --line:#1c2a1c;
    --green:#00ff41; --green-dim:#0c9b30; --txt:#c8e6c8; --muted:#6f8a6f;
    --warn:#ffcc00; --crit:#ff3b3b; --degr:#7a7a7a;
  }}
  /* ── Light-clean theme ── */
  [data-theme='light'] {{
    --bg:#f5f6fa; --panel:#ffffff; --panel2:#f0f2f7; --line:#dde1ea;
    --green:#2563eb; --green-dim:#1d4ed8; --txt:#1a1a2e; --muted:#6b7280;
    --warn:#d97706; --crit:#dc2626; --degr:#9ca3af;
  }}
  [data-theme='light'] body {{
    background-image:none; background-color:var(--bg);
  }}
  [data-theme='light'] .card {{
    background:linear-gradient(180deg,#ffffff,#f0f2f7);
    box-shadow:0 1px 4px rgba(0,0,0,.10);
  }}
  [data-theme='light'] .panelbox {{ background:linear-gradient(180deg,#ffffff,#f0f2f7); }}
  [data-theme='light'] .spark-area {{ fill:rgba(37,99,235,.09); }}
  [data-theme='light'] .sp-warn .spark-area {{ fill:rgba(217,119,6,.09); }}
  [data-theme='light'] .sp-crit .spark-area {{ fill:rgba(220,38,38,.09); }}
  [data-theme='light'] .qbar {{ background:#e5e7eb; }}
  [data-theme='light'] .b-none {{ background:#dde5f0; }}
  [data-theme='light'] .g-track {{ stroke:#e5e7eb; }}
  [data-theme='light'] .cert {{ background:#ffffff; border-color:#dde1ea; }}
  [data-theme='light'] footer {{ color:#9ca3af; }}
  [data-theme='light'] .alerts li {{ background:#fef2f2; color:#7f1d1d; }}
  /* ── Dark NOC scrollbars ── */
  * {{ scrollbar-width:thin; scrollbar-color:var(--green) rgba(0,0,0,.24); }}
  *::-webkit-scrollbar {{ width:6px; height:6px; }}
  *::-webkit-scrollbar-track {{ background:rgba(0,0,0,.24); }}
  *::-webkit-scrollbar-thumb {{ background:var(--green); border-radius:999px; border:1px solid rgba(0,0,0,.35); }}
  *::-webkit-scrollbar-thumb:hover {{ background:var(--green-dim); }}
  /* ── Midnight-blue theme ── */
  [data-theme='midnight'] {{
    --bg:#0d1b2a; --panel:#142236; --panel2:#0f1d2e; --line:#1e3a5f;
    --green:#00d4ff; --green-dim:#0099bb; --txt:#e2f0ff; --muted:#4a6fa5;
    --warn:#ffc107; --crit:#ff5252; --degr:#3a5a7a;
  }}
  [data-theme='midnight'] body {{
    background-image:radial-gradient(circle at 50% 0%, #0f2338 0%, #080e17 70%);
  }}
  [data-theme='midnight'] .card {{ background:linear-gradient(180deg,#142236,#0f1d2e); }}
  [data-theme='midnight'] .panelbox {{ background:linear-gradient(180deg,#142236,#0f1d2e); }}
  [data-theme='midnight'] .spark-area {{ fill:rgba(0,212,255,.13); }}
  [data-theme='midnight'] .qbar {{ background:#0a1825; }}
  [data-theme='midnight'] .b-none {{ background:#0f2030; }}
  [data-theme='midnight'] footer {{ color:#1e3a5f; }}
  /* ── Solarized-dark theme ── */
  [data-theme='solarized'] {{
    --bg:#002b36; --panel:#073642; --panel2:#04303c; --line:#0d4455;
    --green:#859900; --green-dim:#657b00; --txt:#eee8d5; --muted:#586e75;
    --warn:#b58900; --crit:#dc322f; --degr:#657b83;
  }}
  [data-theme='solarized'] body {{
    background-image:radial-gradient(circle at 50% 0%, #073642 0%, #001e27 70%);
  }}
  [data-theme='solarized'] .card {{ background:linear-gradient(180deg,#073642,#04303c); }}
  [data-theme='solarized'] .panelbox {{ background:linear-gradient(180deg,#073642,#04303c); }}
  [data-theme='solarized'] .spark-area {{ fill:rgba(133,153,0,.15); }}
  [data-theme='solarized'] .qbar {{ background:#011f27; }}
  [data-theme='solarized'] .b-none {{ background:#04303c; }}
  [data-theme='solarized'] footer {{ color:#0d3040; }}
  /* ── Dracula theme ── */
  [data-theme='dracula'] {{
    --bg:#282a36; --panel:#21222c; --panel2:#1e1f29; --line:#3d3f4f;
    --green:#50fa7b; --green-dim:#3dcc63; --txt:#f8f8f2; --muted:#6272a4;
    --warn:#f1fa8c; --crit:#ff5555; --degr:#44475a;
  }}
  [data-theme='dracula'] body {{
    background-image:radial-gradient(circle at 50% 0%, #2e3040 0%, #1e1f29 70%);
  }}
  [data-theme='dracula'] .card {{ background:linear-gradient(180deg,#21222c,#1e1f29); }}
  [data-theme='dracula'] .panelbox {{ background:linear-gradient(180deg,#21222c,#1e1f29); }}
  [data-theme='dracula'] .brand h1 {{ color:#bd93f9; text-shadow:0 0 8px rgba(189,147,249,.4); }}
  [data-theme='dracula'] .spark-area {{ fill:rgba(80,250,123,.10); }}
  [data-theme='dracula'] .qbar {{ background:#191a21; }}
  [data-theme='dracula'] .b-none {{ background:#252636; }}
  [data-theme='dracula'] footer {{ color:#3d3f4f; }}
  /* ── Nord theme ── */
  [data-theme='nord'] {{
    --bg:#2e3440; --panel:#3b4252; --panel2:#353c4a; --line:#4c566a;
    --green:#a3be8c; --green-dim:#88a870; --txt:#eceff4; --muted:#616e88;
    --warn:#ebcb8b; --crit:#bf616a; --degr:#4c566a;
  }}
  [data-theme='nord'] body {{
    background-image:radial-gradient(circle at 50% 0%, #3b4252 0%, #242933 70%);
  }}
  [data-theme='nord'] .card {{ background:linear-gradient(180deg,#3b4252,#353c4a); }}
  [data-theme='nord'] .panelbox {{ background:linear-gradient(180deg,#3b4252,#353c4a); }}
  [data-theme='nord'] .brand h1 {{ color:#88c0d0; text-shadow:0 0 8px rgba(136,192,208,.4); }}
  [data-theme='nord'] .spark-area {{ fill:rgba(163,190,140,.13); }}
  [data-theme='nord'] .qbar {{ background:#242933; }}
  [data-theme='nord'] .b-none {{ background:#2a3040; }}
  [data-theme='nord'] footer {{ color:#3b4252; }}
  /* ── Gruvbox-dark theme ── */
  [data-theme='gruvbox'] {{
    --bg:#282828; --panel:#3c3836; --panel2:#32302f; --line:#504945;
    --green:#b8bb26; --green-dim:#98971a; --txt:#ebdbb2; --muted:#928374;
    --warn:#fabd2f; --crit:#fb4934; --degr:#665c54;
  }}
  [data-theme='gruvbox'] body {{
    background-image:radial-gradient(circle at 50% 0%, #3c3836 0%, #1d2021 70%);
  }}
  [data-theme='gruvbox'] .card {{ background:linear-gradient(180deg,#3c3836,#32302f); }}
  [data-theme='gruvbox'] .panelbox {{ background:linear-gradient(180deg,#3c3836,#32302f); }}
  [data-theme='gruvbox'] .brand h1 {{ color:#fabd2f; text-shadow:0 0 8px rgba(250,189,47,.4); }}
  [data-theme='gruvbox'] .spark-area {{ fill:rgba(184,187,38,.12); }}
  [data-theme='gruvbox'] .qbar {{ background:#1d2021; }}
  [data-theme='gruvbox'] .b-none {{ background:#282828; }}
  [data-theme='gruvbox'] footer {{ color:#504945; }}
  /* ── Tokyo Night theme ── */
  [data-theme='tokyo'] {{
    --bg:#1a1b26; --panel:#24283b; --panel2:#1f2335; --line:#3b4261;
    --green:#9ece6a; --green-dim:#73b05a; --txt:#c0caf5; --muted:#565f89;
    --warn:#e0af68; --crit:#f7768e; --degr:#3b4261;
  }}
  [data-theme='tokyo'] body {{
    background-image:radial-gradient(circle at 50% 0%, #24283b 0%, #13141f 70%);
  }}
  [data-theme='tokyo'] .card {{ background:linear-gradient(180deg,#24283b,#1f2335); }}
  [data-theme='tokyo'] .panelbox {{ background:linear-gradient(180deg,#24283b,#1f2335); }}
  [data-theme='tokyo'] .brand h1 {{ color:#7aa2f7; text-shadow:0 0 8px rgba(122,162,247,.4); }}
  [data-theme='tokyo'] .spark-area {{ fill:rgba(122,162,247,.12); }}
  [data-theme='tokyo'] .qbar {{ background:#13141f; }}
  [data-theme='tokyo'] .b-none {{ background:#1a1b26; }}
  [data-theme='tokyo'] footer {{ color:#3b4261; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
    font-family:"SF Mono",Menlo,Consolas,"Roboto Mono",monospace; font-size:14px;
    background-image:radial-gradient(circle at 50% 0%, #0d160d 0%, #060906 70%); }}
  .topbar {{ display:flex; align-items:center; justify-content:space-between;
    padding:14px 22px; border-bottom:1px solid var(--line);
    background:linear-gradient(180deg,#0c130c,#080b08); position:sticky; top:0; z-index:5; }}
  .brand {{ display:flex; align-items:center; gap:14px; }}
  .brand-text {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }}
  .brand-logo {{ width:30px; height:30px; object-fit:contain; border-radius:4px; flex:none; }}
  .brand h1 {{ font-size:20px; margin:0; color:var(--green); letter-spacing:2px;
    text-shadow:0 0 8px rgba(0,255,65,.4); }}
  .brand .tag {{ color:var(--muted); font-size:11px; letter-spacing:3px; }}
  .brand-editable {{ cursor:text; border-bottom:1px dashed transparent; }}
  .brand-editable:hover {{ border-bottom-color:var(--green-dim); }}
  .brand-inline-input {{ background:var(--panel); border:1px solid var(--green-dim); color:var(--txt);
    font:inherit; letter-spacing:inherit; padding:2px 6px; border-radius:4px; outline:none; min-width:180px; }}
  .top-right {{ display:flex; align-items:center; gap:18px; }}
  .ts {{ color:var(--muted); font-size:12px; }}
  .ts b {{ color:var(--txt); }}
  .reports-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.78); z-index:2600; }}
  .reports-panel {{ position:fixed; right:-460px; top:0; bottom:0; width:min(460px,100vw); background:var(--panel);
    border-left:1px solid var(--line); z-index:2601; transition:right .18s ease; padding:18px; overflow:auto; box-shadow:-18px 0 40px rgba(0,0,0,.35); }}
  .reports-panel.open {{ right:0; }}
  .reports-panel-hdr {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; }}
  .reports-title {{ color:var(--green); font-size:13px; letter-spacing:3px; text-transform:uppercase; font-weight:700; }}
  .report-tabs {{ display:grid; grid-template-columns:repeat(4,1fr); gap:6px; margin:10px 0 14px; }}
  .report-tab,.report-action {{ background:var(--panel2); border:1px solid var(--line); color:var(--txt); font:inherit; font-size:10px; padding:7px; border-radius:4px; cursor:pointer; }}
  .report-tab.active,.report-tab:hover,.report-action:hover {{ border-color:var(--green-dim); color:var(--green); }}
  .report-actions {{ display:flex; gap:8px; margin-bottom:14px; }}
  .report-summary {{ border:1px solid var(--line); background:var(--panel2); border-radius:6px; padding:12px; color:var(--txt); font-size:12px; line-height:1.6; }}
  .report-summary h4 {{ margin:0 0 8px; color:var(--green); letter-spacing:2px; text-transform:uppercase; }}
  .report-summary ul {{ margin:8px 0 0 18px; padding:0; }}
  .health {{ display:flex; align-items:center; gap:9px; padding:7px 15px;
    border:1px solid var(--line); border-radius:4px; font-weight:bold; letter-spacing:1px;
    font-size:12px; }}
  .health .led {{ width:12px; height:12px; border-radius:50%; }}
  .h-ok    {{ color:var(--green); border-color:var(--green-dim); }}
  .h-ok .led {{ background:var(--green); box-shadow:0 0 10px var(--green); animation:pulse 2s infinite; }}
  .h-warn  {{ color:var(--warn); border-color:#8a7400; }}
  .h-warn .led {{ background:var(--warn); box-shadow:0 0 10px var(--warn); }}
  .h-crit  {{ color:var(--crit); border-color:#8a1d1d; }}
  .h-crit .led {{ background:var(--crit); box-shadow:0 0 12px var(--crit); animation:pulse 1s infinite; }}
  .h-degraded {{ color:var(--degr); border-color:#3a3a3a; }}
  .h-degraded .led {{ background:var(--degr); }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.35}} }}
  .wrap {{ padding:18px 22px 40px; max-width:1500px; margin:0 auto; }}
  .section-label {{ color:var(--green-dim); font-size:11px; letter-spacing:3px;
    margin:22px 4px 10px; text-transform:uppercase; border-bottom:1px solid var(--line);
    padding-bottom:6px; cursor:pointer; user-select:none; display:flex;
    align-items:center; gap:8px; }}
  .section-label .sec-title {{ flex:1; }}
  .section-collapse-icon {{ font-size:10px; color:var(--muted); transition:transform .2s; flex-shrink:0; }}
  .section-collapsed .section-collapse-icon {{ transform:rotate(-90deg); }}
  .section-drag-handle {{ display:none; cursor:grab; color:var(--muted); font-size:14px;
    padding:0 4px; flex-shrink:0; }}
  .edit-mode .section-drag-handle {{ display:block; }}
  .section-del-btn {{ display:none; background:none; border:none; color:var(--muted);
    font-size:11px; cursor:pointer; padding:0 3px; flex-shrink:0; }}
  .edit-mode .section-del-btn {{ display:block; }}
  .section-del-btn:hover {{ color:var(--crit); }}
  .section-add-btn {{ display:none; background:rgba(0,255,65,.08); border:1px dashed var(--green-dim);
    color:var(--green-dim); padding:6px 16px; border-radius:4px; font-size:10px;
    letter-spacing:2px; cursor:pointer; font-family:inherit; text-transform:uppercase;
    margin:12px 4px; }}
  .edit-mode .section-add-btn {{ display:block; }}
  .section-add-btn:hover {{ border-color:var(--green); color:var(--green);
    background:rgba(0,255,65,.13); }}
  .section-label input.sec-rename {{ background:transparent; border:none; border-bottom:1px solid var(--green);
    color:var(--green-dim); font:inherit; font-size:11px; letter-spacing:3px;
    text-transform:uppercase; outline:none; width:auto; min-width:80px; padding:0; }}
  .row {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; }}
  @media(max-width:1100px){{ .row{{grid-template-columns:repeat(2,1fr);}} }}
  @media(max-width:620px){{ .row{{grid-template-columns:1fr;}} }}
  .card {{ background:linear-gradient(180deg,var(--panel),var(--panel2));
    border:1px solid var(--line); border-left:3px solid var(--degr); border-radius:6px;
    padding:14px 16px; box-shadow:0 2px 10px rgba(0,0,0,.4);
    transition:box-shadow .18s ease,border-color .18s ease,filter .18s ease; cursor:pointer; }}
  .card:hover {{ box-shadow:0 4px 18px rgba(0,0,0,.55),0 0 0 1px var(--line); filter:brightness(1.07); }}
  .card.s-ok:hover {{ box-shadow:0 4px 18px rgba(0,0,0,.5),0 0 8px rgba(0,255,65,.18); border-color:var(--green-dim); }}
  .card.s-warn:hover {{ box-shadow:0 4px 18px rgba(0,0,0,.5),0 0 8px rgba(255,204,0,.18); border-color:var(--warn); }}
  .card.s-crit:hover {{ box-shadow:0 4px 18px rgba(0,0,0,.5),0 0 10px rgba(255,59,59,.25); border-color:var(--crit); }}
  .card.s-ok {{ border-left-color:var(--green); }}
  .card.s-warn {{ border-left-color:var(--warn); }}
  .card.s-crit {{ border-left-color:var(--crit); }}
  .card.s-degraded, .card.s-error {{ border-left-color:var(--degr); }}
  .card-h {{ display:flex; align-items:center; gap:9px; margin-bottom:12px; }}
  .card-h h3 {{ margin:0; font-size:12px; letter-spacing:2px; color:var(--txt); font-weight:600; }}
  .card-h .dot {{ width:8px; height:8px; border-radius:50%; background:var(--degr); }}
  .s-ok .dot {{ background:var(--green); box-shadow:0 0 7px var(--green); }}
  .s-warn .dot {{ background:var(--warn); box-shadow:0 0 7px var(--warn); }}
  .s-crit .dot {{ background:var(--crit); box-shadow:0 0 7px var(--crit); }}
  .card-b {{ display:flex; gap:10px; flex-wrap:wrap; }}
  .metric {{ flex:1; min-width:70px; }}
  .metric .m-v {{ font-size:20px; color:var(--green); font-weight:bold;
    text-shadow:0 0 6px rgba(0,255,65,.25); white-space:nowrap; }}
  .metric .m-l {{ font-size:10px; color:var(--muted); letter-spacing:1px;
    text-transform:uppercase; margin-top:3px; }}
  .metric.m-warn .m-v {{ color:var(--warn); text-shadow:0 0 6px rgba(255,204,0,.25); }}
  .metric.m-crit .m-v {{ color:var(--crit); text-shadow:0 0 6px rgba(255,59,59,.3); }}
  .sub {{ margin-top:11px; padding-top:9px; border-top:1px solid var(--line);
    font-size:11px; color:var(--muted); line-height:1.5; word-break:break-word; }}
  .gauges {{ display:flex; flex-wrap:wrap; gap:10px; justify-content:flex-start; }}
  .gauge {{ width:140px; }}
  .gauge svg {{ width:140px; height:140px; }}
  .g-track {{ fill:none; stroke:#15201510; stroke:#162016; stroke-width:11; }}
  .g-val {{ fill:none; stroke-width:11; stroke-linecap:round; transition:stroke-dasharray .5s; }}
  .g-ok .g-val {{ stroke:var(--green); filter:drop-shadow(0 0 4px rgba(0,255,65,.5)); }}
  .g-warn .g-val {{ stroke:var(--warn); filter:drop-shadow(0 0 4px rgba(255,204,0,.5)); }}
  .g-crit .g-val {{ stroke:var(--crit); filter:drop-shadow(0 0 4px rgba(255,59,59,.5)); }}
  .g-pct {{ fill:var(--txt); font-size:22px; text-anchor:middle; font-weight:bold; }}
  .g-ok .g-pct {{ fill:var(--green); }}
  .g-warn .g-pct {{ fill:var(--warn); }}
  .g-crit .g-pct {{ fill:var(--crit); }}
  .g-lbl {{ fill:var(--muted); font-size:10px; text-anchor:middle; letter-spacing:.5px; }}
  .certs {{ display:flex; flex-wrap:wrap; gap:12px; }}
  .cert {{ background:var(--panel); border:1px solid var(--line); border-radius:6px;
    padding:14px 18px; min-width:130px; text-align:center; border-top:3px solid var(--green); }}
  .cert.c-ok {{ border-top-color:var(--green); }}
  .cert.c-warn {{ border-top-color:var(--warn); }}
  .cert.c-crit {{ border-top-color:var(--crit); }}
  .cert-d {{ font-size:26px; font-weight:bold; color:var(--green); }}
  .c-warn .cert-d {{ color:var(--warn); }}
  .c-crit .cert-d {{ color:var(--crit); }}
  .cert-n {{ font-size:11px; color:var(--muted); margin-top:5px; word-break:break-word; }}
  .alerts {{ list-style:none; margin:0; padding:0; }}
  .alerts li {{ background:var(--panel); border-left:3px solid var(--crit);
    padding:9px 14px; margin-bottom:7px; border-radius:4px; font-size:13px; color:#ffd9d9; }}
  .empty {{ color:var(--muted); font-size:12px; padding:14px; font-style:italic; }}
  .ok-empty {{ color:var(--green-dim); }}
  .twocol {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
  @media(max-width:900px){{ .twocol{{grid-template-columns:1fr;}} }}
  .card-full {{ grid-column:1 / -1; }}
  .card-half {{ grid-column:span 2; }}
  @media(max-width:900px) {{ .card-half {{ grid-column:1 / -1; }} }}
  .panelbox {{ background:transparent; border:none; padding:0; margin:0; }}
  .panelbox h4 {{ margin:0 0 12px; font-size:11px; letter-spacing:2px; color:var(--green-dim); }}
  /* sparkline trend */
  .trend {{ width:100%; margin-top:10px; padding-top:9px; border-top:1px dashed var(--line); }}
  .trend-lbl {{ font-size:9px; color:var(--muted); letter-spacing:1px; text-transform:uppercase; display:block; margin-bottom:3px; }}
  .spark {{ width:100%; height:34px; display:block; }}
  .spark-line {{ fill:none; stroke:var(--green); stroke-width:1.6; }}
  .spark-area {{ fill:rgba(0,255,65,.08); stroke:none; }}
  .spark-dot {{ fill:var(--green); }}
  .sp-warn .spark-line {{ stroke:var(--warn); }} .sp-warn .spark-area {{ fill:rgba(255,204,0,.08); }} .sp-warn .spark-dot {{ fill:var(--warn); }}
  .sp-crit .spark-line {{ stroke:var(--crit); }} .sp-crit .spark-area {{ fill:rgba(255,59,59,.08); }} .sp-crit .spark-dot {{ fill:var(--crit); }}
  .spark-empty {{ font-size:10px; color:var(--muted); font-style:italic; padding:8px 0; }}
  /* UniFi device list */
  .dvlist {{ width:100%; margin-top:10px; padding-top:9px; border-top:1px dashed var(--line); }}
  .dv {{ display:flex; align-items:center; gap:8px; padding:3px 0; font-size:11px; }}
  .dv-dot {{ width:7px; height:7px; border-radius:50%; background:var(--green); box-shadow:0 0 5px var(--green); flex:none; }}
  .dv-off .dv-dot {{ background:var(--crit); box-shadow:0 0 5px var(--crit); }}
  .dv-name {{ color:var(--txt); flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .dv-kind {{ color:var(--muted); font-size:9px; text-transform:uppercase; letter-spacing:1px; width:88px; text-align:right; }}
  .dv-up {{ color:var(--green-dim); font-size:10px; width:64px; text-align:right; }}
  .dv-off .dv-up {{ color:var(--crit); }}
  /* URBackup client list */
  .ublist {{ width:100%; margin-top:10px; padding-top:9px; border-top:1px dashed var(--line); }}
  .ubrow {{ display:flex; justify-content:space-between; gap:10px; padding:3px 0; font-size:11px; align-items:baseline; }}
  .ubrow .ub-n {{ color:var(--txt); white-space:nowrap; flex:0 0 auto; }}
  .ubrow .ub-a {{ color:var(--green-dim); white-space:nowrap; text-align:right; flex:1 1 auto;
    overflow:hidden; text-overflow:ellipsis; }}
  .ubrow.m-warn .ub-a {{ color:var(--warn); }} .ubrow.m-crit .ub-a {{ color:var(--crit); }}
  .ubrow.m-warn .ub-n, .ubrow.m-crit .ub-n {{ color:#ffd9d9; }}
  /* QNAP cards */
  .qsec-l {{ width:100%; font-size:9px; letter-spacing:2px; color:var(--green-dim);
    text-transform:uppercase; margin:12px 0 6px; border-bottom:1px solid var(--line); padding-bottom:3px; }}
  .qvol {{ width:100%; margin-bottom:9px; }}
  .qvol-top {{ display:flex; justify-content:space-between; font-size:11px; color:var(--txt); margin-bottom:3px; }}
  .qvol-pct {{ font-weight:bold; }}
  .qbar {{ height:7px; background:#0c140c; border:1px solid var(--line); border-radius:4px; overflow:hidden; }}
  .qbar-f {{ display:block; height:100%; background:var(--green); }}
  .qvol-cap {{ font-size:9px; color:var(--muted); margin-top:2px; }}
  .q-ok {{ color:var(--green); }} .q-warn {{ color:var(--warn); }} .q-crit {{ color:var(--crit); }}
  .qbar-f.q-ok {{ background:var(--green); }} .qbar-f.q-warn {{ background:var(--warn); }} .qbar-f.q-crit {{ background:var(--crit); }}
  .qdisk {{ display:flex; align-items:center; gap:8px; font-size:11px; padding:2px 0; width:100%; }}
  .qd-dot {{ width:7px; height:7px; border-radius:50%; background:var(--green); box-shadow:0 0 5px var(--green); flex:none; }}
  .qdisk.q-crit .qd-dot {{ background:var(--crit); box-shadow:0 0 5px var(--crit); }}
  .qd-n {{ flex:1; color:var(--txt); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .qd-h {{ width:60px; text-align:right; }} .qdisk.q-ok .qd-h {{ color:var(--green); }} .qdisk.q-crit .qd-h {{ color:var(--crit); }}
  .qd-t {{ width:48px; text-align:right; color:var(--muted); font-size:10px; }}
  /* Uptime Kuma 24h history bars */
  .hbar-row, .hbar-head {{ display:flex; align-items:center; gap:10px; margin-bottom:5px; }}
  .hbar-name {{ width:170px; font-size:11px; color:var(--txt); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:none; }}
  .hbar-cells {{ display:flex; gap:2px; flex:1; }}
  .hbar {{ display:inline-block; width:13px; height:18px; border-radius:2px; flex:1; min-width:6px; }}
  .hbar-head .hbar {{ width:13px; height:13px; flex:none; min-width:13px; vertical-align:middle; margin:0 2px 0 8px; }}
  .hbar-legend {{ font-size:10px; color:var(--muted); letter-spacing:1px; }}
  .b-up {{ background:var(--green-dim); }}
  .b-down {{ background:var(--crit); }}
  .b-other {{ background:var(--warn); }}
  .b-none {{ background:#1a241a; }}
  footer {{ text-align:center; color:#2c402c; font-size:10px; padding:20px;
    letter-spacing:2px; }}
  /* theme toggle button */
  .theme-btn {{ background:none; border:1px solid var(--line); color:var(--muted);
    cursor:pointer; padding:5px 12px; border-radius:4px; font-size:12px;
    font-family:inherit; letter-spacing:1px; transition:border-color .2s,color .2s; }}
  .theme-btn:hover {{ border-color:var(--green); color:var(--green); }}
  .nav-svg {{ width:16px; height:16px; display:block; stroke:currentColor; fill:none; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }}
  #intel-btn {{ display:inline-flex; align-items:center; justify-content:center; padding:5px 9px; }}
  #intel-btn:hover .nav-svg {{ color:var(--green); filter:drop-shadow(0 0 4px rgba(0,255,65,.35)); }}
  .svc-link {{ display:block; color:var(--green-dim); text-decoration:none; font-size:11px; letter-spacing:1px; text-transform:uppercase; }}
  .svc-link:hover {{ color:var(--green); text-decoration:underline; }}
  /* ── Ticker / scrolling info bar ── */
  .ticker-bar {{
    display:flex; align-items:center;
    background:linear-gradient(90deg,#050905,#080e08,#050905);
    border-bottom:1px solid var(--line);
    height:32px; overflow:hidden; position:sticky; top:50px; z-index:4;
    transition:height .2s ease, opacity .2s ease, border-width .2s ease;
  }}
  .ticker-bar.ticker-hidden {{
    height:0 !important; opacity:0; border-bottom-width:0; overflow:hidden;
  }}
  #ticker-toggle-btn.ticker-active {{ color:var(--green); border-color:var(--green); }}
  .tk-badge {{
    flex:none; font-size:10px; font-weight:bold; letter-spacing:2px;
    padding:0 14px; height:100%; display:flex; align-items:center;
    border-right:1px solid var(--line); white-space:nowrap;
    min-width:72px; justify-content:center;
  }}
  .tb-ok   {{ color:var(--green);  background:rgba(0,255,65,.07);  }}
  .tb-warn {{ color:var(--warn);   background:rgba(255,204,0,.09); }}
  .tb-crit {{ color:var(--crit);   background:rgba(255,59,59,.12); animation:pulse 1.2s infinite; }}
  .tk-track {{
    flex:1; overflow:hidden; height:100%;
    -webkit-mask-image:linear-gradient(90deg,transparent,#000 3%,#000 97%,transparent);
    mask-image:linear-gradient(90deg,transparent,#000 3%,#000 97%,transparent);
  }}
  .tk-content {{
    display:inline-flex; align-items:center; height:100%;
    white-space:nowrap;
    animation:ticker-scroll 60s linear infinite;
  }}
  @keyframes ticker-scroll {{
    0%   {{ transform:translateX(0); }}
    100% {{ transform:translateX(-50%); }}
  }}
  .tk-item {{
    font-size:11px; letter-spacing:.5px; padding:0 4px;
  }}
  .t-ok   {{ color:var(--green-dim); }}
  .t-info {{ color:var(--muted); }}
  .t-warn {{ color:var(--warn); }}
  .t-crit {{ color:var(--crit); font-weight:bold; }}
  .tk-sep {{
    color:var(--line); margin:0 14px; font-size:10px; flex:none;
  }}
  /* card modal */
  .card-modal {{ display:none; position:fixed; top:0; left:0; right:0; bottom:0;
    background:rgba(0,0,0,0.82); backdrop-filter:blur(4px); z-index:9000;
    align-items:center; justify-content:center; }}
  .card-modal-box {{ background:var(--panel); border:1px solid var(--line);
    border-radius:8px; padding:24px; max-width:780px; width:92%; max-height:85vh;
    overflow-y:auto; position:relative; box-shadow:0 8px 32px rgba(0,0,0,0.6); }}
  .card-modal-close {{ position:absolute; top:10px; right:14px; background:none;
    border:none; color:var(--muted); font-size:20px; cursor:pointer;
    line-height:1; padding:4px; }}
  .card-modal-close:hover {{ color:var(--green); }}
  .card-modal-title {{ font-size:16px; font-weight:700; color:var(--green);
    letter-spacing:0.1em; text-transform:uppercase; margin-bottom:16px;
    padding-right:32px; }}
  .card-modal-body {{ font-size:13px; color:var(--txt); }}
  /* alert panel */
  .alert-overlay {{ display:none; position:fixed; top:0; left:0; right:0; bottom:0;
    background:rgba(0,0,0,0.4); z-index:8000; }}
  .alert-panel {{ position:fixed; top:0; right:-400px; width:380px; height:100vh;
    background:var(--panel); border-left:1px solid var(--line); z-index:8001;
    display:flex; flex-direction:column; transition:right 0.3s ease;
    box-shadow:-4px 0 20px rgba(0,0,0,0.5); }}
  .alert-panel.open {{ right:0; }}
  .alert-panel-hdr {{ display:flex; align-items:center; justify-content:space-between;
    padding:12px 16px; border-bottom:1px solid var(--line);
    font-size:11px; letter-spacing:0.12em; color:var(--green); font-weight:700; }}
  .alert-panel-hdr button {{ background:none; border:1px solid var(--line);
    color:var(--muted); cursor:pointer; padding:3px 8px; font-size:11px;
    border-radius:3px; }}
  .alert-panel-hdr button:hover {{ color:var(--green); border-color:var(--green); }}
  .alert-feed {{ list-style:none; margin:0; padding:8px; overflow-y:auto; flex:1; }}
  .alert-feed li {{ display:flex; flex-direction:column; gap:2px;
    padding:8px 10px; border-bottom:1px solid var(--line);
    font-size:12px; }}
  .alert-feed li:last-child {{ border-bottom:none; }}
  .ah-ts {{ color:var(--muted); font-size:10px; letter-spacing:0.06em; }}
  .ah-text {{ color:var(--txt); }}
  .alert-panel-empty {{ color:var(--muted); font-size:12px; text-align:center;
    padding:32px 16px; }}
  .bell-badge {{ background:var(--crit); color:#fff; border-radius:50%;
    font-size:9px; padding:1px 4px; margin-left:3px;
    display:none; vertical-align:super; }}
  /* ── Edit mode ── */
  .edit-mode .row {{ outline:1px dashed var(--green-dim); outline-offset:4px; }}
  .edit-mode .card {{ cursor:grab !important; position:relative; }}
  .edit-mode .card:active {{ cursor:grabbing !important; }}
  .sortable-ghost {{ opacity:0.35; outline:2px solid var(--green) !important; }}
  .sortable-drag {{ opacity:0.9; box-shadow:0 8px 24px rgba(0,255,65,0.35) !important; }}
  #edit-btn.active {{ color:var(--green); border-color:var(--green); background:rgba(0,255,65,0.08); }}
  .card-rm-btn {{ display:none; position:absolute; top:4px; right:4px; z-index:10;
    background:rgba(255,51,51,.85); border:none; color:#fff; width:18px; height:18px;
    border-radius:3px; font-size:12px; line-height:18px; text-align:center;
    cursor:pointer; padding:0; font-weight:700; }}
  .edit-mode .card-rm-btn {{ display:block; }}
  .card-rm-btn:hover {{ background:var(--crit); }}
  .card-resize-btn {{ display:none; position:absolute; top:4px; right:26px; z-index:10;
    background:rgba(0,80,40,.85); border:1px solid var(--green-dim); color:var(--green);
    width:18px; height:18px; border-radius:3px; font-size:10px; line-height:16px;
    text-align:center; cursor:pointer; padding:0; font-weight:700; }}
  .edit-mode .card-resize-btn {{ display:block; }}
  /* ── Settings / integrations overlay ── */
  .settings-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,0.88);
    backdrop-filter:blur(4px); z-index:9500; padding:20px; box-sizing:border-box; }}
  .settings-overlay.open {{ display:flex; align-items:center; justify-content:center; }}
  .settings-shell {{ display:flex; flex-direction:column; width:100%; max-width:960px;
    max-height:88vh; background:var(--panel); border-radius:8px;
    box-shadow:0 8px 60px rgba(0,0,0,.85); overflow:hidden; border:1px solid var(--line); }}
  .settings-modal-hdr {{ display:flex; align-items:center; justify-content:space-between;
    padding:12px 18px; border-bottom:1px solid var(--line); background:var(--panel2);
    flex-shrink:0; }}
  .settings-modal-title {{ font-size:11px; font-weight:700; letter-spacing:3px;
    color:var(--green); text-transform:uppercase; }}
  .settings-modal-sub {{ font-size:9px; color:var(--muted); margin-top:1px; }}
  .settings-modal-close {{ background:none; border:none; color:var(--muted);
    font-size:20px; cursor:pointer; padding:0 4px; line-height:1; }}
  .settings-modal-close:hover {{ color:var(--green); }}
  .settings-body {{ display:flex; flex:1; overflow:hidden; }}
  .settings-sidebar {{ width:200px; flex-shrink:0; background:var(--panel2);
    border-right:1px solid var(--line); overflow-y:auto; display:flex;
    flex-direction:column; }}
  .settings-sidebar-hdr {{ padding:14px 14px 8px; border-bottom:1px solid var(--line); }}
  .settings-sidebar-title {{ font-size:11px; font-weight:700; letter-spacing:3px;
    color:var(--green); text-transform:uppercase; }}
  .settings-sidebar-sub {{ font-size:9px; color:var(--muted); margin-top:2px; }}
  .sidebar-cat {{ padding:10px 14px 3px; font-size:9px; letter-spacing:2px;
    color:var(--green-dim); text-transform:uppercase; font-weight:700; }}
  .sidebar-item {{ display:flex; align-items:center; justify-content:space-between;
    padding:6px 14px; cursor:pointer; font-size:11px; color:var(--txt);
    border-left:2px solid transparent; transition:background .1s; }}
  .sidebar-item:hover {{ background:rgba(0,255,65,.06); color:var(--green); }}
  .sidebar-item.active {{ background:rgba(0,255,65,.09); color:var(--green);
    border-left-color:var(--green); font-weight:700; }}
  .sidebar-dot {{ width:6px; height:6px; border-radius:50%; flex-shrink:0; background:var(--degr); }}
  .sidebar-dot.ok {{ background:var(--green); box-shadow:0 0 4px var(--green); }}
  .sidebar-dot.warn {{ background:var(--warn); }}
  .sidebar-dot.error, .sidebar-dot.crit {{ background:var(--crit); }}
  .sidebar-check {{ width:14px; height:14px; accent-color:var(--green); cursor:pointer; }}
  .gear-menu {{ position:relative; display:inline-flex; align-items:center; }}
  .gear-user-display {{ padding:5px 12px 7px; color:var(--muted); text-transform:uppercase; cursor:default; user-select:none; }}
  .gear-user-display b {{ display:block; color:var(--muted); font-size:11px; letter-spacing:1px; opacity:.82; font-weight:700; }}
  .gear-user-role {{ display:block; color:var(--muted); font-size:9px; margin-top:2px; letter-spacing:1px; opacity:.68; }}
  .auth-user-divider {{ height:1px; background:var(--line); margin:5px 0; }}
  .auth-user-logout {{ width:100%; background:none; border:none; color:var(--green); font-family:inherit;
    font-size:11px; letter-spacing:1px; text-align:left; padding:7px 12px; cursor:pointer; text-transform:uppercase; }}
  .auth-user-logout:hover {{ background:rgba(0,255,65,.08); color:var(--txt); }}
  .gear-dropdown {{ display:none; position:absolute; right:0; top:calc(100% + 6px); min-width:165px; background:var(--panel); border:1px solid var(--line); border-radius:5px; box-shadow:0 8px 28px rgba(0,0,0,.85); z-index:10050; padding:7px 0; }}
  .gear-menu.open .gear-dropdown {{ display:block; }}
  .gear-dropdown button {{ width:100%; background:none; border:none; color:var(--green); font-family:inherit; font-size:11px; letter-spacing:1px; text-align:left; padding:7px 12px; cursor:pointer; text-transform:uppercase; }}
  .gear-dropdown button:hover {{ background:rgba(0,255,65,.08); color:var(--txt); }}
  #intel-btn,#settings-gear-btn {{ min-width:34px; padding-left:8px; padding-right:8px; text-align:center; }}
  .edit-mode .top-right {{ gap:8px; }}
  .edit-mode .ts {{ display:none; }}
  .edit-mode .theme-btn {{ padding-left:9px; padding-right:9px; }}
  .viewer-role #edit-btn,.viewer-role #save-btn,.viewer-role #cancel-edit-btn,.viewer-role #add-card-btn,.viewer-role #add-custom-card-btn {{ display:none!important; }}
  .user-table {{ width:100%; border-collapse:collapse; font-size:11px; margin:10px 0 16px; }}
  .user-table th,.user-table td {{ border-bottom:1px solid var(--line); padding:7px; text-align:left; }}
  .user-table th {{ color:var(--green-dim); text-transform:uppercase; letter-spacing:1px; font-size:9px; }}
  .settings-content {{ flex:1; overflow-y:auto; padding:22px 28px; position:relative; }}
  .settings-close {{ display:none; }}
  .settings-welcome {{ color:var(--muted); font-size:12px; padding-top:60px;
    text-align:center; letter-spacing:1px; }}
  .settings-welcome-icon {{ font-size:32px; display:block; margin-bottom:12px; opacity:.3; }}
  .integ-form-title {{ font-size:13px; font-weight:700; letter-spacing:2px;
    color:var(--green); margin-bottom:6px; text-transform:uppercase; }}
  .integ-form-status {{ display:inline-flex; align-items:center; gap:6px; font-size:10px;
    letter-spacing:1px; text-transform:uppercase; margin-bottom:18px; padding:4px 10px;
    border-radius:3px; background:var(--panel2); border:1px solid var(--line); }}
  .form-section-hdr {{ grid-column:1/-1; font-size:9px; font-weight:700; letter-spacing:2px;
    text-transform:uppercase; color:var(--green-dim); padding:10px 0 4px;
    border-bottom:1px solid var(--line); margin-top:6px; }}
  .form-section-hdr:first-child {{ margin-top:0; }}
  .form-field.span2 {{ grid-column:1/-1; }}
  .form-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:12px 20px; }}
  @media(max-width:700px) {{ .form-grid {{ grid-template-columns:1fr; }} }}
  .form-field {{ display:flex; flex-direction:column; gap:4px; }}
  .form-field label {{ font-size:10px; color:var(--muted); letter-spacing:1px; text-transform:uppercase; }}
  .form-field input, .form-field select {{ background:var(--panel); border:1px solid var(--line); color:var(--txt);
    padding:6px 10px; border-radius:4px; font-size:12px; font-family:inherit;
    transition:border-color .15s; box-sizing:border-box; width:100%; }}
  .form-field input:focus, .form-field select:focus {{ outline:none; border-color:var(--green); box-shadow:0 0 0 1px rgba(0,255,65,.16); }}
  .form-field select option {{ background:var(--panel); color:var(--txt); }}
  .form-field input::placeholder {{ color:var(--muted); opacity:.5; }}
  .form-actions {{ display:flex; gap:10px; margin-top:16px; align-items:center; }}
  .btn-test {{ background:none; border:1px solid var(--green-dim); color:var(--green-dim);
    padding:6px 16px; border-radius:4px; font-size:11px; font-family:inherit;
    cursor:pointer; letter-spacing:1px; transition:all .15s; }}
  .btn-test:hover {{ border-color:var(--green); color:var(--green); }}
  .btn-test:disabled {{ opacity:.4; cursor:default; }}
  .btn-save {{ background:var(--green); border:none; color:#000;
    padding:6px 16px; border-radius:4px; font-size:11px; font-family:inherit;
    cursor:pointer; font-weight:700; letter-spacing:1px; transition:opacity .15s; }}
  .btn-save:hover {{ opacity:.85; }}
  .btn-save:disabled {{ opacity:.4; cursor:default; }}
  .test-result {{ font-size:11px; padding:4px 10px; border-radius:3px; }}
  .test-result.ok {{ color:var(--green); background:rgba(0,255,65,.08); }}
  .test-result.error {{ color:var(--crit); background:rgba(255,59,59,.08); }}
  .test-result.testing {{ color:var(--muted); }}
  .badge-soon {{ font-size:8px; font-weight:700; letter-spacing:1px;
    text-transform:uppercase; padding:1px 5px; border-radius:2px;
    background:rgba(0,255,65,.10); color:var(--green); border:1px solid var(--green-dim);
    flex-shrink:0; }}
  .badge-custom {{ font-size:8px; font-weight:700; letter-spacing:1px;
    text-transform:uppercase; padding:1px 5px; border-radius:2px;
    background:rgba(0,255,65,.10); color:var(--green); border:1px solid var(--green-dim);
    flex-shrink:0; }}
  .sidebar-item.coming-soon {{ opacity:.9; }}
  .sidebar-item.coming-soon:hover {{ opacity:1; }}
  .coming-soon-panel {{ padding:0; text-align:left; }}
  .coming-soon-icon {{ font-size:18px; display:inline-block; margin-right:8px; opacity:.45; }}
  .coming-soon-title {{ font-size:14px; font-weight:700; letter-spacing:2px; color:var(--txt);
    text-transform:uppercase; margin-bottom:6px; display:inline-block; }}
  .coming-soon-msg {{ font-size:11px; color:var(--muted); line-height:1.6; margin:8px 0 16px;
    padding:8px 10px; background:var(--panel2); border-radius:4px; border-left:3px solid var(--green-dim); }}
  .custom-panel {{ padding:4px 0 12px; }}
  .custom-panel-note {{ font-size:11px; color:var(--muted); margin-bottom:16px;\n    padding:8px 10px; background:var(--panel2); border-radius:4px; border-left:3px solid var(--green-dim); }}
{cc_css}
{intel_css}

  /* ── First-launch welcome overlay ── */
  .welcome-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.92);
    backdrop-filter:blur(6px); z-index:10000; align-items:center; justify-content:center; }}
  .welcome-overlay.open {{ display:flex; }}
  .welcome-box {{ background:var(--panel); border:1px solid var(--line); border-radius:10px;
    max-width:480px; width:calc(100% - 40px); padding:36px 32px 28px; text-align:center;
    box-shadow:0 12px 60px rgba(0,0,0,.9); }}
  .welcome-logo {{ font-size:38px; margin-bottom:12px; }}
  .welcome-title {{ font-size:16px; font-weight:700; letter-spacing:3px; color:var(--green);
    text-transform:uppercase; margin-bottom:6px; }}
  .welcome-sub {{ font-size:11px; color:var(--muted); letter-spacing:1px; margin-bottom:24px; line-height:1.7; }}
  .welcome-actions {{ display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }}
  .welcome-btn-primary {{ background:var(--green); border:none; color:#000; padding:9px 24px;
    border-radius:5px; font-size:11px; font-weight:700; letter-spacing:2px; cursor:pointer;
    font-family:inherit; text-transform:uppercase; }}
  .welcome-btn-primary:hover {{ opacity:.85; }}
  .welcome-btn-skip {{ background:none; border:1px solid var(--line); color:var(--muted);
    padding:9px 24px; border-radius:5px; font-size:11px; letter-spacing:2px; cursor:pointer;
    font-family:inherit; text-transform:uppercase; }}
  .welcome-btn-skip:hover {{ border-color:var(--muted); color:var(--txt); }}
</style></head>
<body>
  <div class="topbar">
    <div class="brand">
      {dashboard_logo}<div class="brand-text"><h1 id="brand-title" class="brand-editable" title="Click to edit dashboard title" data-config-key="dashboard_title">{dashboard_title}</h1><span id="brand-subtitle" class="tag brand-editable" title="Click to edit dashboard subtitle" data-config-key="dashboard_subtitle">{dashboard_subtitle}</span></div>
    </div>
    <div class="top-right">
      <div class="ts">UPDATED <b>{ts}</b></div>
      <div class="health h-{overall}"><span class="led"></span>{overall_txt}</div>
      <button id="alert-bell" class="theme-btn" onclick="toggleAlertPanel()" title="Alert history">&#128276;<span id="bell-badge" class="bell-badge"></span></button>
      <button id="intel-btn" class="theme-btn" onclick="toggleIntel(true)" title="NOC Intelligence" aria-label="NOC Intelligence"><svg class="nav-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-5"/><path d="M12 16V8"/><path d="M16 16v-7"/><path d="M20 16v-3"/></svg></button>
      <button id="save-btn" class="theme-btn" onclick="saveLayout()" title="Save layout" style="display:none;background:var(--green);color:#000;font-weight:700;border-color:var(--green)">&#10003; SAVE</button>
      <button id="cancel-edit-btn" class="theme-btn" onclick="cancelEditMode()" title="Cancel edit mode without saving" style="display:none;border-color:var(--crit);color:var(--crit)">&#10005; CANCEL</button>
      {cc_btn}
      <div id="gear-menu" class="gear-menu">
        <button id="settings-gear-btn" class="theme-btn" onclick="toggleGearMenu(event)" title="Dashboard menu" aria-label="Dashboard menu">&#9881;&#9662;</button>
        <div class="gear-dropdown" role="menu">
          <div class="gear-user-display" aria-label="Signed in user"><b id="gear-user-name">USER</b><span id="gear-user-role" class="gear-user-role">ROLE</span></div>
          <div class="auth-user-divider"></div>
          <button type="button" onclick="toggleGearMenu(false);logoutUser()" role="menuitem">Logout</button>
          <button id="edit-btn" type="button" onclick="toggleGearMenu(false);toggleEditMode()" role="menuitem">Edit Dashboard</button>
          <button id="settings-btn" type="button" onclick="toggleGearMenu(false);toggleSettings()" role="menuitem">Settings</button>
        </div>
      </div>
      <button id="theme-btn" class="theme-btn" onclick="toggleTheme()" title="Cycle theme">&#9680;</button>
    </div>
  </div>
  {ticker_bar}
  <div class="wrap">
    <div class="section-label">System Status</div>
    <div class="row">{row1}</div>
    <div class="section-label">Security &amp; Network</div>
    <div class="row">{row2}</div>
    <div class="section-label">Media &amp; Downloads</div>
    <div class="row">{media_row}</div>
    <div class="section-label">System Tools</div>
    <div class="row">{system_tools_row}</div>
    <div class="section-label">QNAP Storage Appliances</div>
    <div class="row">{qnap_cards}</div>
    <div class="section-label">Proxmox Storage Utilization</div>
    <div class="row"><div class="card card-full" data-card-id="proxmox-storage"><h3>PROXMOX STORAGE</h3><div class="panelbox">{row3}</div></div></div>
    <div class="section-label">Uptime History (last 24h)</div>
    <div class="row"><div class="card card-full" data-card-id="kuma-history"><h3>UPTIME HISTORY</h3><div class="panelbox">{kuma_history}</div></div></div>
    <div class="section-label">Certificates &amp; Active Alerts</div>
    <div class="row">
      <div class="card card-half" data-card-id="cert-expiry"><h3>TLS CERT EXPIRY</h3><div class="panelbox"><div class="certs">{cert_tiles}</div></div></div>
      <div class="card card-half" data-card-id="active-alerts"><h3>ACTIVE ALERTS</h3><div class="panelbox">{alert_block}</div></div>
    </div>
  </div>
  <button class="section-add-btn" id="add-section-btn" onclick="addSection()">&#10010; Add Section</button>
  <div id="card-modal" class="card-modal" onclick="closeCardModal(event)">
    <div class="card-modal-box">
      <button class="card-modal-close" onclick="closeCardModal(null)">&times;</button>
      <div id="card-modal-title" class="card-modal-title"></div>
      <div id="card-modal-body" class="card-modal-body"></div>
    </div>
  </div>
  <div id="reports-overlay" class="reports-overlay" onclick="if(typeof _nocBackdropClick!=='function'||_nocBackdropClick(event,this,'#reports-panel'))toggleReports(false)"></div>
  <div id="reports-panel" class="reports-panel">
    <div class="reports-panel-hdr">
      <div class="reports-title">Reports</div>
      <button class="theme-btn" onclick="toggleReports(false)">&times;</button>
    </div>
    <div class="report-tabs">
      <button class="report-tab active" data-range="hourly" onclick="renderReport('hourly')">Hourly</button>
      <button class="report-tab" data-range="daily" onclick="renderReport('daily')">Daily</button>
      <button class="report-tab" data-range="weekly" onclick="renderReport('weekly')">Weekly</button>
      <button class="report-tab" data-range="monthly" onclick="renderReport('monthly')">Monthly</button>
    </div>
    <div class="report-actions">
      <button class="report-action" onclick="downloadReportCSV()">Download CSV</button>
      <button class="report-action" onclick="downloadReportPDF()">Download PDF</button>
    </div>
    <div id="report-summary" class="report-summary"></div>
  </div>
  <div id="alert-overlay" class="alert-overlay" onclick="toggleAlertPanel()"></div>
  <div id="alert-panel" class="alert-panel">
    <div class="alert-panel-hdr">
      <span>ALERT HISTORY</span>
      <button onclick="clearAlertHistory()">CLEAR</button>
      <button onclick="toggleAlertPanel()">&times;</button>
    </div>
    <ul id="alert-feed" class="alert-feed"></ul>
    <div class="alert-panel-empty" id="alert-empty">No alert history recorded yet.</div>
  </div>
  {cc_overlay}
  {intel_panel}
  <!-- Settings / Integrations overlay -->
  <div id="settings-overlay" class="settings-overlay" onclick="settingsOverlayClick(event)">
    <div class="settings-shell">
      <div class="settings-modal-hdr">
        <div>
          <div class="settings-modal-title">&#9881; Integrations &amp; Settings</div>
          <div class="settings-modal-sub">Configure credentials for all integrations</div>
        </div>
        <button class="settings-modal-close" onclick="toggleSettings()" title="Close">&times;</button>
      </div>
      <div class="settings-body">
        <div class="settings-sidebar">
          <div class="settings-sidebar-hdr">
            <div class="settings-sidebar-title">Settings</div>
            <div class="settings-sidebar-sub">General and integrations</div>
          </div>
          <div id="settings-sidebar-list"></div>
          <div style="padding:10px 14px 14px;border-top:1px solid var(--line);margin-top:auto;">
            <div style="font-size:9px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;">Help</div>
            <div class="sidebar-item" style="padding:5px 0;font-size:10px;" onclick="openSetupWizard()" title="Show the first-launch welcome screen">
              <span>&#9654; Setup Wizard</span>
            </div>
          </div>
        </div>
        <div class="settings-content">
          <button class="settings-close" onclick="toggleSettings()">&times;</button>
          <div id="settings-right">
            <div class="settings-welcome">
              <span class="settings-welcome-icon">&#9881;</span>
              Select an integration from the sidebar to configure credentials.
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
    <!-- First-launch welcome overlay -->
  <div id="welcome-overlay" class="welcome-overlay">
    <div class="welcome-box">
      <div class="welcome-logo">&#9881;</div>
      <div class="welcome-title">Welcome to NOC Dashboard</div>
      <div class="welcome-sub">
        Your homelab operations center is running.<br>
        Open Settings to configure integrations &amp; credentials,<br>
        or explore the dashboard as-is.
      </div>
      <div class="welcome-actions">
        <button class="welcome-btn-primary" onclick="welcomeOpenSettings()">&#9881; Open Settings</button>
        <button class="welcome-btn-skip" onclick="welcomeSkip()">Skip for now</button>
      </div>
    </div>
  </div>
  <footer>MRDTECH INFRASTRUCTURE MONITORING · AUTO-REFRESH 60s · REGEN 15m</footer>
<script>
(function() {{
  var THEMES = ['dark','light','midnight','solarized','dracula','nord','gruvbox','tokyo'];
  var LABELS = {{dark:'DARK',light:'LIGHT',midnight:'MIDNIGHT',solarized:'SOLAR',dracula:'DRACULA',nord:'NORD',gruvbox:'GRUVBOX',tokyo:'TOKYO'}};
  var DEFAULT_THEME = 'dark';

  var _nocLastActivity = Date.now();
  ['click','keydown','pointerdown','wheel','touchstart'].forEach(function(evt){{document.addEventListener(evt,function(){{_nocLastActivity=Date.now();}},{{passive:true}});}});
  function _nocUiBusy(){{
    return document.body.classList.contains('edit-mode')
      || !!document.querySelector('.settings-overlay.open,.intel-panel.open,.intel-modal.open,.alert-panel.open,.reports-panel.open')
      || (Date.now() - _nocLastActivity) < 15000;
  }}
  setInterval(function(){{ if(!_nocUiBusy()) location.reload(); }}, 60000);

  function applyTheme(t) {{
    if (THEMES.indexOf(t) === -1) t = DEFAULT_THEME;
    document.documentElement.setAttribute('data-theme', t);
    var btn = document.getElementById('theme-btn');
    if (btn) btn.textContent = '\u25d0 ' + (LABELS[t] || t.toUpperCase());
  }}

  window.toggleTheme = function() {{
    var cur = document.documentElement.getAttribute('data-theme') || DEFAULT_THEME;
    var idx = THEMES.indexOf(cur);
    var next = THEMES[(idx + 1) % THEMES.length];
    applyTheme(next);
    localStorage.setItem('theme-pin', next);
  }};

  var pin = localStorage.getItem('theme-pin');
  applyTheme(pin && THEMES.indexOf(pin) !== -1 ? pin : DEFAULT_THEME);

  /* ── Ticker bar toggle ── */
  var TICKER_PREF_KEY = 'noc-ticker-visible';
  function _applyTickerPref(visible) {{
    var tb = document.getElementById('ticker-bar');
    var btn = document.getElementById('ticker-toggle-btn');
    if (!tb) return;
    if (visible) {{
      tb.classList.remove('ticker-hidden');
      if (btn) btn.classList.add('ticker-active');
    }} else {{
      tb.classList.add('ticker-hidden');
      if (btn) btn.classList.remove('ticker-active');
    }}
  }}
  window.setTickerVisibility = function(visible) {{
    visible = !!visible;
    _applyTickerPref(visible);
    localStorage.setItem(TICKER_PREF_KEY, visible ? '1' : '0');
    if (DASHBOARD_CONFIG) DASHBOARD_CONFIG.show_ticker_bar = visible;
    document.querySelectorAll('.sidebar-check').forEach(function(cb) {{ cb.checked = visible; }});
    var panelCheck = document.getElementById('settings-toggle-alerts');
    if (panelCheck) panelCheck.checked = visible;
    fetch('/save-dashboard-config', {{method:'POST', headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify(Object.assign({{}}, DASHBOARD_CONFIG || {{}}, {{show_ticker_bar: visible}}))
    }}).catch(function(){{}});
  }};
  window.toggleTickerBar = function() {{
    var tb = document.getElementById('ticker-bar');
    if (!tb) return;
    var isHidden = tb.classList.contains('ticker-hidden');
    window.setTickerVisibility(isHidden); // toggling: if hidden now, make visible
  }};
  // Init from localStorage (instant, no flicker) — server-rendered class handles SSR
  (function() {{
    var stored = localStorage.getItem(TICKER_PREF_KEY);
    if (stored !== null) {{
      _applyTickerPref(stored === '1');
    }} else {{
      // No preference stored — read from current DOM state (server rendered)
      var tb = document.getElementById('ticker-bar');
      if (tb) {{
        var serverVisible = !tb.classList.contains('ticker-hidden');
        localStorage.setItem(TICKER_PREF_KEY, serverVisible ? '1' : '0');
        _applyTickerPref(serverVisible);
      }}
    }}
  }})();

  window.focusCard = function(el) {{
    var title = el.getAttribute('data-title');
    var state = el.getAttribute('data-state');
    var body = el.querySelector('.card-b');
    var modal = document.getElementById('card-modal');
    document.getElementById('card-modal-title').textContent = title;
    var mb = document.getElementById('card-modal-body');
    mb.innerHTML = body ? body.innerHTML : '';
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
  }};
  window.closeCardModal = function(evt) {{
    var modal = document.getElementById('card-modal');
    if (evt && typeof _nocBackdropClick === 'function') {{
      if (!_nocBackdropClick(evt, modal, '.card-modal-box')) return;
    }} else if (evt && evt.target !== modal) return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
  }};
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') closeCardModal(null);
  }});

  function updateFavicon() {{
    var health = document.querySelector('.health');
    var color = '#555555';
    if (health) {{
      if (health.classList.contains('h-ok')) color = '#00ff41';
      else if (health.classList.contains('h-warn')) color = '#ffcc00';
      else if (health.classList.contains('h-crit')) color = '#ff3b3b';
      else if (health.classList.contains('h-degraded')) color = '#7a7a7a';
    }}
    var svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="' + color + '"/></svg>';
    var el = document.getElementById('noc-favicon');
    if (el) el.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
  }}
  updateFavicon();

  function _escapeHtml(s) {{ return String(s||'').replace(/[&<>"']/g, function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}}); }}
  function collectReportData(range) {{
    var cards = Array.from(document.querySelectorAll('.card')).map(function(card){{
      var title = (card.querySelector('h3')||{{}}).textContent || card.getAttribute('data-title') || 'Card';
      var state = card.getAttribute('data-state') || (card.className.match(/s-([a-z]+)/)||[])[1] || 'unknown';
      var sub = (card.querySelector('.sub')||{{}}).textContent || '';
      return {{title:title.trim(), state:state, note:sub.trim()}};
    }});
    var counts = cards.reduce(function(a,c){{a[c.state]=(a[c.state]||0)+1;return a;}},{{}});
    var alerts=[]; try {{ alerts=JSON.parse(localStorage.getItem(ALERT_KEY)||'[]'); }} catch(e) {{}}
    return {{range:range||'hourly', generated:new Date().toISOString(), total:cards.length, counts:counts, cards:cards, alerts:alerts}};
  }}
  function renderReport(range) {{
    window._currentReportRange = range || window._currentReportRange || 'hourly';
    document.querySelectorAll('.report-tab').forEach(function(b){{ b.classList.toggle('active', b.dataset.range === window._currentReportRange); }});
    var d = collectReportData(window._currentReportRange);
    var bad = d.cards.filter(function(c){{ return ['crit','error','warn','degraded'].indexOf(c.state) !== -1; }}).slice(0,12);
    var html = '<h4>'+_escapeHtml(window._currentReportRange)+' Summary</h4>'
      + '<div>Generated: '+_escapeHtml(new Date(d.generated).toLocaleString())+'</div>'
      + '<div>Total cards: '+d.total+'</div>'
      + '<div>OK: '+(d.counts.ok||0)+' · Warn: '+(d.counts.warn||0)+' · Critical/Error: '+((d.counts.crit||0)+(d.counts.error||0))+' · Degraded: '+(d.counts.degraded||0)+'</div>'
      + '<div>Recorded alerts: '+d.alerts.length+'</div>';
    if (bad.length) html += '<ul>'+bad.map(function(c){{return '<li><b>'+_escapeHtml(c.state.toUpperCase())+'</b> '+_escapeHtml(c.title)+(c.note?' — '+_escapeHtml(c.note):'')+'</li>';}}).join('')+'</ul>';
    else html += '<div style="margin-top:8px;color:var(--green)">No non-green cards in the current dashboard snapshot.</div>';
    var el=document.getElementById('report-summary'); if(el) el.innerHTML=html;
  }}
  window.renderReport = renderReport;
  window.renderSettingsReport = function(range) {{
    window._currentReportRange = range || 'daily';
    document.querySelectorAll('#settings-right .report-tab').forEach(function(b){{ b.classList.toggle('active', b.dataset.range === window._currentReportRange); }});
    var d = collectReportData(window._currentReportRange);
    var bad = d.cards.filter(function(c){{ return ['crit','error','warn','degraded'].indexOf(c.state) !== -1; }}).slice(0,12);
    var html = '<h4>'+_escapeHtml(window._currentReportRange)+' Summary</h4>'
      + '<div>Generated: '+_escapeHtml(new Date(d.generated).toLocaleString())+'</div>'
      + '<div>Total cards: '+d.total+'</div>'
      + '<div>OK: '+(d.counts.ok||0)+' · Warn: '+(d.counts.warn||0)+' · Critical/Error: '+((d.counts.crit||0)+(d.counts.error||0))+' · Degraded: '+(d.counts.degraded||0)+'</div>'
      + '<div>Recorded alerts: '+d.alerts.length+'</div>';
    if (bad.length) html += '<ul>'+bad.map(function(c){{return '<li><b>'+_escapeHtml(c.state.toUpperCase())+'</b> '+_escapeHtml(c.title)+(c.note?' — '+_escapeHtml(c.note):'')+'</li>';}}).join('')+'</ul>';
    else html += '<div style="margin-top:8px;color:var(--green)">No non-green cards in the current dashboard snapshot.</div>';
    var el=document.getElementById('settings-report-summary'); if(el) el.innerHTML=html;
  }};
  window.toggleReports = function(force) {{
    var panel=document.getElementById('reports-panel'), ov=document.getElementById('reports-overlay'); if(!panel||!ov) return;
    var open = force === undefined ? !panel.classList.contains('open') : !!force;
    panel.classList.toggle('open', open); ov.style.display = open ? 'block' : 'none';
    if(open) renderReport(window._currentReportRange || 'hourly');
  }};
  window.downloadReportCSV = function() {{
    var d=collectReportData(window._currentReportRange || 'hourly');
    var rows=[['range','generated','title','state','note']].concat(d.cards.map(function(c){{return [d.range,d.generated,c.title,c.state,c.note];}}));
    var csv=rows.map(function(r){{return r.map(function(v){{return '"'+String(v||'').replace(/"/g,'""')+'"';}}).join(',');}}).join('\\n');
    var a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}})); a.download='noc-report-'+d.range+'.csv'; a.click(); setTimeout(function(){{URL.revokeObjectURL(a.href);}},1000);
  }};
  window.downloadReportPDF = function() {{ window.print(); }};

  function saveInlineBranding(key, value) {{
    var vals = Object.assign({{}}, DASHBOARD_CONFIG || {{}});
    vals[key] = value;
    fetch('/save-dashboard-config',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(vals)}})
      .then(function(r){{return r.json();}})
      .then(function(d){{ DASHBOARD_CONFIG=d.config||vals; }})
      .catch(function(e){{ console.warn('Inline branding save failed', e); }});
  }}
  function initInlineBranding() {{
    document.querySelectorAll('.brand-editable').forEach(function(el){{
      el.addEventListener('click', function(){{
        if (el.querySelector('input')) return;
        var key=el.dataset.configKey, old=el.textContent.trim();
        var inp=document.createElement('input'); inp.className='brand-inline-input'; inp.value=old;
        el.textContent=''; el.appendChild(inp); inp.focus(); inp.select();
        function commit(save){{ var val=(inp.value||'').trim()||old; el.textContent=val; if(save && val!==old) saveInlineBranding(key,val); }}
        inp.addEventListener('keydown', function(e){{ if(e.key==='Enter') commit(true); if(e.key==='Escape') commit(false); }});
        inp.addEventListener('blur', function(){{ commit(true); }});
      }});
    }});
  }}
  initInlineBranding();

  var ALERT_KEY = 'noc-alert-history';
  var MAX_ALERTS = 100;
  function loadAlertHistory() {{ return JSON.parse(localStorage.getItem(ALERT_KEY) || '[]'); }}
  function saveAlertHistory(h) {{ localStorage.setItem(ALERT_KEY, JSON.stringify(h)); }}
  function ingestCurrentAlerts() {{
    var items = document.querySelectorAll('.alerts li');
    if (!items.length) return;
    var history = loadAlertHistory();
    var existing = new Set(history.map(function(x) {{ return x.text; }}));
    var ts = new Date().toISOString();
    var added = false;
    items.forEach(function(li) {{
      var text = li.textContent.trim();
      if (!text) return;
      if (!existing.has(text)) {{
        history.unshift({{ text: text, ts: ts }});
        existing.add(text);
        added = true;
      }}
    }});
    if (added) {{
      if (history.length > MAX_ALERTS) history = history.slice(0, MAX_ALERTS);
      saveAlertHistory(history);
    }}
  }}
  function renderAlertHistory() {{
    var history = loadAlertHistory();
    var feed = document.getElementById('alert-feed');
    var empty = document.getElementById('alert-empty');
    if (!feed) return;
    feed.innerHTML = '';
    if (!history.length) {{
      if (empty) empty.style.display = 'block';
      return;
    }}
    if (empty) empty.style.display = 'none';
    history.forEach(function(item) {{
      var li = document.createElement('li');
      var d = new Date(item.ts);
      var ts_str = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], {{hour:'2-digit',minute:'2-digit'}});
      li.innerHTML = '<span class="ah-ts">' + ts_str + '</span><span class="ah-text">' + item.text + '</span>';
      feed.appendChild(li);
    }});
    var badge = document.getElementById('bell-badge');
    if (badge) {{ badge.textContent = history.length > 9 ? '9+' : String(history.length); badge.style.display = history.length ? 'inline-block' : 'none'; }}
  }}
  window.toggleAlertPanel = function() {{
    var panel = document.getElementById('alert-panel');
    var overlay = document.getElementById('alert-overlay');
    var open = panel.classList.toggle('open');
    if (overlay) overlay.style.display = open ? 'block' : 'none';
    if (open) renderAlertHistory();
  }};
  window.clearAlertHistory = function() {{
    localStorage.removeItem(ALERT_KEY);
    renderAlertHistory();
  }};
  ingestCurrentAlerts();
  renderAlertHistory();

  /* ── Edit mode + SortableJS layout persistence ── */
  var LAYOUT_KEY = 'noc-layout';
  var _sortables = [];

  function destroySortables() {{
    _sortables.forEach(function(s) {{ try {{ s.destroy(); }} catch(e) {{}} }});
    _sortables = [];
  }}

  function initSortables() {{
    destroySortables();
    document.querySelectorAll('.row').forEach(function(row) {{
      if (typeof Sortable !== 'undefined') {{
        _sortables.push(Sortable.create(row, {{
          animation: 150,
          ghostClass: 'sortable-ghost',
          dragClass: 'sortable-drag',
          onEnd: function() {{
            // Persist immediately after each drag
            persistLayout();
          }}
        }}));
      }}
    }});
  }}

  window.persistLayout = function persistLayout() {{
    var layout = {{}};
    document.querySelectorAll('.section-label').forEach(function(lbl) {{
      var section = lbl.textContent.trim();
      var row = lbl.nextElementSibling;
      if (row && row.classList.contains('row')) {{
        layout[section] = Array.from(row.children).map(function(card) {{
          return card.querySelector('h3') ? card.querySelector('h3').textContent.trim() : '';
        }}).filter(Boolean);
      }}
    }});
    try {{ localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); }} catch(e) {{}}
  }}

  function applyStoredLayout() {{
    var stored;
    try {{ stored = JSON.parse(localStorage.getItem(LAYOUT_KEY) || 'null'); }} catch(e) {{ return; }}
    if (!stored) return;
    document.querySelectorAll('.section-label').forEach(function(lbl) {{
      var section = lbl.textContent.trim();
      if (!stored[section]) return;
      var row = lbl.nextElementSibling;
      if (!row || !row.classList.contains('row')) return;
      var order = stored[section];
      var cards = Array.from(row.children);
      order.forEach(function(title) {{
        var card = cards.find(function(c) {{
          var h3 = c.querySelector('h3');
          return h3 && h3.textContent.trim() === title;
        }});
        if (card) row.appendChild(card);
      }});
    }});
  }}

  window.toggleEditMode = function() {{
    var body = document.body;
    var editBtn = document.getElementById('edit-btn');
    var saveBtn = document.getElementById('save-btn');
    var cancelBtn = document.getElementById('cancel-edit-btn');
    var isEdit = body.classList.toggle('edit-mode');
    if (isEdit) {{
      window._editLayoutSnapshot = localStorage.getItem(LAYOUT_KEY);
      window._editSectionSnapshot = localStorage.getItem(SEC_KEY);
    }}
    if (editBtn) {{ editBtn.classList.toggle('active', isEdit); editBtn.textContent = isEdit ? 'Editing' : 'Edit Dashboard'; }}
    if (saveBtn) saveBtn.style.display = isEdit ? 'inline-block' : 'none';
    if (cancelBtn) cancelBtn.style.display = isEdit ? 'inline-block' : 'none';
    if (isEdit) {{
      // Inject remove + resize buttons into every card
      document.querySelectorAll('.card').forEach(function(card) {{
        if (!card.querySelector('.card-rm-btn')) {{
          var rmBtn = document.createElement('button');
          rmBtn.className = 'card-rm-btn';
          rmBtn.title = 'Remove card';
          rmBtn.textContent = '✕';
          rmBtn.addEventListener('click', function(e) {{
            e.stopPropagation();
            if (confirm('Remove this card? (Reload page to restore)')) {{
              card.remove();
              persistLayout();
            }}
          }});
          card.appendChild(rmBtn);
        }}
        if (!card.querySelector('.card-resize-btn')) {{
          var rsBtn = document.createElement('button');
          rsBtn.className = 'card-resize-btn';
          rsBtn.title = 'Cycle size';
          rsBtn.textContent = '⤢';
          rsBtn.addEventListener('click', function(e) {{
            e.stopPropagation();
            var sizes = ['', 'card-wide', 'card-full', 'card-half'];
            var cur = sizes.find(function(s) {{ return s && card.classList.contains(s); }}) || '';
            var next = sizes[(sizes.indexOf(cur) + 1) % sizes.length];
            sizes.forEach(function(s) {{ if (s) card.classList.remove(s); }});
            if (next) card.classList.add(next);
            persistLayout();
          }});
          card.appendChild(rsBtn);
        }}
      }});
      if (typeof Sortable === 'undefined') {{
        var s = document.createElement('script');
        s.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.3/Sortable.min.js';
        s.onload = function() {{ initSortables(); }};
        document.head.appendChild(s);
      }} else {{
        initSortables();
      }}
    }} else {{
      // Remove injected buttons
      document.querySelectorAll('.card-rm-btn, .card-resize-btn').forEach(function(btn) {{ btn.remove(); }});
      destroySortables();
    }}
  }};

  window.saveLayout = function() {{
    persistLayout();
    window._editLayoutSnapshot = null;
    window._editSectionSnapshot = null;
    window.toggleEditMode();
  }};

  window.cancelEditMode = function() {{
    if (!document.body.classList.contains('edit-mode')) return;
    if (window._editLayoutSnapshot === null || window._editLayoutSnapshot === undefined) localStorage.removeItem(LAYOUT_KEY);
    else localStorage.setItem(LAYOUT_KEY, window._editLayoutSnapshot);
    if (window._editSectionSnapshot === null || window._editSectionSnapshot === undefined) localStorage.removeItem(SEC_KEY);
    else localStorage.setItem(SEC_KEY, window._editSectionSnapshot);
    window._editLayoutSnapshot = null;
    window._editSectionSnapshot = null;
    location.reload();
  }};

  // Apply saved layout on page load (before user edits)
  applyStoredLayout();

  /* ── Section Management ── */
  var SEC_KEY = 'noc-sections';
  var _sectionSortable = null;

  function _getSections() {{
    return Array.from(document.querySelectorAll('.section-label'));
  }}

  function _getSectionRows(lbl) {{
    // Return all sibling .row elements immediately following this label
    var rows = [];
    var el = lbl.nextElementSibling;
    while (el && el.classList.contains('row')) {{
      rows.push(el);
      el = el.nextElementSibling;
    }}
    return rows;
  }}

  function _initSectionLabels() {{
    _getSections().forEach(function(lbl) {{
      // Wrap text in span if not already done
      if (!lbl.querySelector('.sec-title')) {{
        var titleText = lbl.textContent.trim();
        lbl.innerHTML =
          '<span class="section-drag-handle" title="Drag to reorder">&#8942;&#8942;</span>'\
          +'<span class="sec-title">'+titleText+'</span>'\
          +'<span class="section-collapse-icon">&#9660;</span>'\
          +'<button class="section-del-btn" title="Delete section">&#128465;</button>';
      }}
      // Click to collapse (but not when clicking buttons inside)
      lbl.onclick = function(e) {{
        if (e.target.classList.contains('section-del-btn')) {{ return; }}
        if (e.target.classList.contains('section-drag-handle')) {{ return; }}
        if (e.target.classList.contains('sec-rename')) {{ return; }}
        var rows = _getSectionRows(lbl);
        var isCollapsed = lbl.classList.toggle('section-collapsed');
        rows.forEach(function(r) {{ r.style.display = isCollapsed ? 'none' : ''; }});
        _persistSectionState();
      }};
      // Double-click sec-title to rename
      var titleSpan = lbl.querySelector('.sec-title');
      if (titleSpan) {{
        titleSpan.ondblclick = function(e) {{
          e.stopPropagation();
          var cur = titleSpan.textContent.trim();
          var inp = document.createElement('input');
          inp.className = 'sec-rename';
          inp.value = cur;
          titleSpan.textContent = '';
          titleSpan.appendChild(inp);
          inp.focus();
          inp.select();
          function _commit() {{
            var val = inp.value.trim() || cur;
            titleSpan.textContent = val;
            _persistSectionState();
          }}
          inp.onblur = _commit;
          inp.onkeydown = function(ev) {{
            if (ev.key === 'Enter') {{ inp.blur(); }}
            if (ev.key === 'Escape') {{ inp.value = cur; inp.blur(); }}
          }};
        }};
      }}
      // Delete button
      var delBtn = lbl.querySelector('.section-del-btn');
      if (delBtn) {{
        delBtn.onclick = function(e) {{
          e.stopPropagation();
          var titleText = (lbl.querySelector('.sec-title')||lbl).textContent.trim();
          if (!confirm('Delete section "'+titleText+'"? Cards will move to the last section.')) return;
          var rows = _getSectionRows(lbl);
          // Find or create Unsorted section
          var labels = _getSections();
          var lastLabel = labels[labels.length - 1];
          var targetRow = lastLabel ? _getSectionRows(lastLabel)[0] : null;
          if (!targetRow) {{
            // Create Unsorted section
            window.addSection('Unsorted');
            labels = _getSections();
            lastLabel = labels[labels.length - 1];
            targetRow = _getSectionRows(lastLabel)[0];
          }}
          rows.forEach(function(row) {{
            Array.from(row.children).forEach(function(card) {{
              if (targetRow) targetRow.appendChild(card);
            }});
            row.remove();
          }});
          lbl.remove();
          _persistSectionState();
          persistLayout();
          if (document.body.classList.contains('edit-mode')) {{
            destroySortables(); initSortables();
          }}
        }};
      }}
    }});
  }}

  function _persistSectionState() {{
    var state = {{}};
    _getSections().forEach(function(lbl) {{
      var title = (lbl.querySelector('.sec-title')||lbl).textContent.trim();
      state[title] = {{ collapsed: lbl.classList.contains('section-collapsed') }};
    }});
    // Save section order
    state['__order__'] = _getSections().map(function(lbl) {{
      return (lbl.querySelector('.sec-title')||lbl).textContent.trim();
    }});
    try {{ localStorage.setItem(SEC_KEY, JSON.stringify(state)); }} catch(e) {{}}
  }}

  function _applySectionState() {{
    var stored;
    try {{ stored = JSON.parse(localStorage.getItem(SEC_KEY)||'null'); }} catch(e) {{ return; }}
    if (!stored) return;
    _getSections().forEach(function(lbl) {{
      var title = (lbl.querySelector('.sec-title')||lbl).textContent.trim();
      if (stored[title] && stored[title].collapsed) {{
        lbl.classList.add('section-collapsed');
        _getSectionRows(lbl).forEach(function(r) {{ r.style.display = 'none'; }});
      }}
    }});
  }}

  window.addSection = function(name) {{
    var title = name || prompt('Section name:', 'New Section');
    if (!title) return;
    var wrap = document.querySelector('.wrap');
    if (!wrap) return;
    var lbl = document.createElement('div');
    lbl.className = 'section-label';
    lbl.innerHTML =
      '<span class="section-drag-handle" title="Drag to reorder">&#8942;&#8942;</span>'\
      +'<span class="sec-title">'+title+'</span>'\
      +'<span class="section-collapse-icon">&#9660;</span>'\
      +'<button class="section-del-btn" title="Delete section">&#128465;</button>';
    var row = document.createElement('div');
    row.className = 'row';
    var addBtn = document.getElementById('add-section-btn');
    if (addBtn) {{
      wrap.insertBefore(row, addBtn);
      wrap.insertBefore(lbl, row);
    }} else {{
      wrap.appendChild(lbl);
      wrap.appendChild(row);
    }}
    _initSectionLabels();
    _persistSectionState();
    if (document.body.classList.contains('edit-mode')) {{
      destroySortables(); initSortables();
      if (_sectionSortable) {{ _sectionSortable.destroy(); }}
      _initSectionSort();
    }}
  }};

  function _initSectionSort() {{
    var wrap = document.querySelector('.wrap');
    if (!wrap || typeof Sortable === 'undefined') return;
    _sectionSortable = Sortable.create(wrap, {{
      handle: '.section-drag-handle',
      animation: 150,
      ghostClass: 'sortable-ghost',
      filter: '.row,.card',
      preventOnFilter: false,
      onEnd: function() {{
        _persistSectionState();
        persistLayout();
      }}
    }});
  }}

  // Patch toggleEditMode to handle section sort
  var _origToggleEditMode = window.toggleEditMode;
  window.toggleEditMode = function() {{
    var ret = _origToggleEditMode.apply(this, arguments);
    var isEdit = document.body.classList.contains('edit-mode');
    if (isEdit) {{
      if (typeof Sortable !== 'undefined') {{
        if (_sectionSortable) {{ _sectionSortable.destroy(); }}
        _initSectionSort();
      }} else {{
        // Sortable loads async — init section sort after it loads
        var existing = document.querySelector('script[src*="sortablejs"]');
        if (existing) {{
          existing.addEventListener('load', function() {{
            if (_sectionSortable) {{ _sectionSortable.destroy(); }}
            _initSectionSort();
          }});
        }}
      }}
    }} else {{
      if (_sectionSortable) {{ _sectionSortable.destroy(); _sectionSortable = null; }}
    }}
    return ret;
  }};

  // Init on load
  _initSectionLabels();
  _applySectionState();
  var INTEGRATIONS = {integrations_json};
  var DASHBOARD_CONFIG = {dashboard_config_json};
  var NOC_HEALTH_CURRENT = {health_current_json};
  var _fieldDefs = null;
  var _currentCfg = null;
  var _selectedType = null;
  var CURRENT_USER = null;

  var CATEGORIES = [
    {{ id:'account',    label:'Account', keys:['account_change_password','account_sessions','account_2fa','account_api_tokens','account_manage_users','account_login_history','account_password_expiry'] }},
    {{ id:'general',    label:'General', keys:['general_dashboard', 'datetime_settings', 'reports', 'toggle_alerts'] }},
    {{ id:'infra',      label:'Infrastructure',
      keys:['proxmox','docker','pbs','kuma','urbackup','hyperv','smart'] }},
    {{ id:'security',   label:'Security',
      keys:['wazuh','crowdsec','limacharlie','cloudflare','malware_sources','sophos','meraki'] }},
    {{ id:'network',    label:'Network',
      keys:['unifi','wan','npm','adguard','adguard2','tailscale','wgdashboard','mikrotik','openwrt','snmp'] }},
    {{ id:'vpn',        label:'VPN',
      keys:['zerotier','twingate','netbird','headscale','pangolin'] }},
    {{ id:'storage',    label:'Storage', keys:['qnap','truenas','unraid','synology'] }},
    {{ id:'media',      label:'Media',
      keys:['plex','tautulli','sonarr','radarr','lidarr','sabnzbd','seerr','prowlarr','jellyfin','emby'] }},
    {{ id:'monitoring', label:'Monitoring', keys:['homeassistant','netdata','glances','speedtest_tracker','node_exporter'] }},
    {{ id:'homelab',    label:'Homelab Apps',
      keys:['nextcloud','gitea','traefik','caddy','authentik','authelia','pihole'] }},
    {{ id:'hypervisors',label:'Hypervisors',
      keys:['vmware','xcpng','libvirt','pfsense','opnsense'] }},
    {{ id:'microsoft',  label:'Microsoft',
      keys:['intune','entra','m365','azure_vms','exchange','sharepoint'] }},
    {{ id:'hardware',   label:'Hardware',
      keys:['ipmi','ilo','idrac'] }},
    {{ id:'cloud',      label:'Cloud',
      keys:['aws','gcp','digitalocean','linode'] }},
    {{ id:'custom',     label:'Custom', keys:['custom'] }},
    {{ id:'email_sec',  label:'Email Security',
      keys:['proofpoint','mimecast','barracuda','msdefender_email'] }},
    {{ id:'dns_web',    label:'DNS & Web Security',
      keys:['cisco_umbrella','zscaler','cf_gateway'] }},
    {{ id:'dns_alt',    label:'DNS Servers',
      keys:['technitium','blocky','coredns'] }},
    {{ id:'endpoint',   label:'Endpoint Security',
      keys:['crowdstrike','sentinelone','sophos_central','msdefender_ep','eset','bitdefender','malwarebytes'] }},
    {{ id:'firewall',   label:'Firewall',
      keys:['fortigate','paloalto','checkpoint','watchguard','sonicwall','cisco_asa'] }},
    {{ id:'siem',       label:'SIEM',
      keys:['splunk','elastic','graylog','datadog'] }},
    {{ id:'vuln',       label:'Vulnerability',
      keys:['qualys','rapid7','openvas'] }},
    {{ id:'identity',   label:'Identity',
      keys:['okta','duo','jumpcloud','onelogin'] }},
    {{ id:'backup',     label:'Backup',
      keys:['veeam','acronis','commvault','datto'] }},
    {{ id:'ticketing',  label:'Ticketing',
      keys:['servicenow','zendesk','freshdesk','connectwise_psa'] }},
    {{ id:'rmm',        label:'RMM',
      keys:['cw_automate','datto_rmm','ninjarmm','atera'] }},
    {{ id:'containers', label:'Containers',
      keys:['kubernetes','rancher','nomad'] }},
    {{ id:'databases',  label:'Databases',
      keys:['mysql','postgresql','redis','mongodb','mariadb'] }},
    {{ id:'mon_ext',    label:'Monitoring Platforms',
      keys:['zabbix','nagios','checkmk','librenms','prtg','uptimerobot'] }},
    {{ id:'storage_ext',label:'Storage',
      keys:['minio','ceph'] }},
    {{ id:'selfhosted', label:'Self-Hosted',
      keys:['paperless','vaultwarden','gotify','ntfy','bookstack','wikijs'] }},
  ];

  function _integByKey(k) {{ return INTEGRATIONS.find(function(i){{return i.key===k;}}); }}
  function _stateColor(s) {{
    return s==='ok'?'ok':s==='warn'?'warn':(s==='error'||s==='crit')?'error':'degraded';
  }}

  function _envPrefix(key) {{
    return String(key || 'integration').toUpperCase().replace(/[^A-Z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'INTEGRATION';
  }}
  function _defaultFieldsFor(key) {{
    var p = _envPrefix(key);
    return [
      {{key:p+'_URL',      label:'URL',      type:'text'}},
      {{key:p+'_API_KEY',  label:'API Key',  type:'password'}},
      {{key:p+'_USERNAME', label:'Username', type:'text'}},
      {{key:p+'_PASSWORD', label:'Password', type:'password'}}
    ];
  }}
  function _fieldsFor(defs, key) {{
    var fields = (defs && defs[key]) || [];
    return fields.length ? fields : _defaultFieldsFor(key);
  }}

  function _loadFieldDefs(cb) {{
    if (_fieldDefs) {{ cb(_fieldDefs); return; }}
    fetch('/api/integration-fields').then(function(r){{return r.json();}})
      .then(function(d){{_fieldDefs=d;cb(d);}}).catch(function(){{cb({{}});}});
  }}
  function _loadCurrentCfg(cb) {{
    fetch('/api/current-config').then(function(r){{return r.json();}})
      .then(function(d){{_currentCfg=d;cb(d);}}).catch(function(){{cb({{}});}});
  }}

  function buildSidebar() {{
    var list = document.getElementById('settings-sidebar-list');
    if (!list) return;
    var html = '';
    // Render the full menu while auth is still loading. Server-side auth still
    // enforces permissions; this prevents the sidebar from appearing empty while
    // unrelated API calls finish. Once auth returns, viewers are rebuilt down to
    // account-only.
    var isAdmin = !CURRENT_USER || CURRENT_USER.role === 'admin';
    var cats = isAdmin ? CATEGORIES : [{{id:'account', label:'Account', keys:['account_change_password','account_sessions','account_2fa','account_api_tokens']}}];
    cats.forEach(function(cat) {{
      var items = cat.keys.filter(function(k) {{
        if (k === 'account_manage_users' || k === 'account_login_history' || k === 'account_password_expiry') return isAdmin;
        if (k.indexOf('account_') === 0) return true;
        if (k === 'custom' || k === 'general_dashboard' || k === 'datetime_settings' || k === 'reports' || k === 'toggle_alerts') return true;
        var i = _integByKey(k);
        return !!i;
      }});
      if (!items.length) return;
      html += '<div class="sidebar-cat">'+cat.label+'</div>';
      items.forEach(function(key) {{
        if (key === 'account_change_password') {{
          html += '<div class="sidebar-item" data-key="account_change_password"><span>Change Password</span><span class="sidebar-dot ok"></span></div>';
          return;
        }}
        if (key === 'account_sessions') {{ html += '<div class="sidebar-item" data-key="account_sessions"><span>Sessions</span><span class="sidebar-dot ok"></span></div>'; return; }}
        if (key === 'account_2fa') {{ html += '<div class="sidebar-item" data-key="account_2fa"><span>Two-Factor Auth</span><span class="sidebar-dot ok"></span></div>'; return; }}
        if (key === 'account_api_tokens') {{ html += '<div class="sidebar-item" data-key="account_api_tokens"><span>API Tokens</span><span class="sidebar-dot ok"></span></div>'; return; }}
        if (key === 'account_manage_users') {{ html += '<div class="sidebar-item" data-key="account_manage_users"><span>Manage Users</span><span class="sidebar-dot ok"></span></div>'; return; }}
        if (key === 'account_login_history') {{ html += '<div class="sidebar-item" data-key="account_login_history"><span>Login History</span><span class="sidebar-dot ok"></span></div>'; return; }}
        if (key === 'account_password_expiry') {{ html += '<div class="sidebar-item" data-key="account_password_expiry"><span>Password Expiry</span><span class="sidebar-dot ok"></span></div>'; return; }}
        if (key === 'general_dashboard') {{
          html += '<div class="sidebar-item" data-key="general_dashboard">'            +'<span>Dashboard Branding</span>'            +'<span class="sidebar-dot ok"></span>'            +'</div>';
          return;
        }}
        if (key === 'datetime_settings') {{
          html += '<div class="sidebar-item" data-key="datetime_settings">'            +'<span>Date &amp; Time</span>'            +'<span class="sidebar-dot ok"></span>'            +'</div>';
          return;
        }}
        if (key === 'reports') {{
          html += '<div class="sidebar-item" data-key="reports">'            +'<span>Reports</span>'            +'<span class="sidebar-dot ok"></span>'            +'</div>';
          return;
        }}
        if (key === 'toggle_alerts') {{
          var tickerVisible = (DASHBOARD_CONFIG || {{}}).show_ticker_bar !== false;
          try {{ var storedTicker = localStorage.getItem(TICKER_PREF_KEY); if (storedTicker !== null) tickerVisible = storedTicker === '1'; }} catch(e) {{}}
          html += '<div class="sidebar-item" data-key="toggle_alerts">'            +'<span>Toggle Alerts</span>'            +'<input type="checkbox" class="sidebar-check" '+(tickerVisible?'checked':'')+' onclick="event.stopPropagation(); setTickerVisibility(this.checked);">'            +'</div>';
          return;
        }}
        if (key === 'custom') {{
          html += '<div class="sidebar-item" data-key="custom">'\
            +'<span>Custom Integration</span>'\
            +'<span class="badge-custom">+NEW</span>'\
            +'</div>';
          return;
        }}
        var integ = _integByKey(key);
        if (!integ) return;
        var isSoon = integ.state === 'coming_soon';
        var sc = isSoon ? 'degraded' : _stateColor(integ.state);
        html += '<div class="sidebar-item'+(isSoon?' coming-soon':'')+'" data-key="'+key+'">'\
          +'<span>'+integ.label+'</span>';
        if (isSoon) {{
          html += '<span class="badge-soon">READY</span>';
        }} else {{
          html += '<span class="sidebar-dot '+sc+'"></span>';
        }}
        html += '</div>';
      }});
    }});
    list.innerHTML = html;
    list.onclick = function(e) {{
      var item = e.target.closest('.sidebar-item');
      if (item) selectInteg(item.dataset.key);
    }};
  }}

  function selectInteg(key) {{
    _selectedType = key;
    document.querySelectorAll('.sidebar-item').forEach(function(el) {{
      el.classList.toggle('active', el.dataset.key === key);
    }});
    var right = document.getElementById('settings-right');
    if (!right) return;

    // Account panels
    if (key === 'account_change_password') {{
      right.innerHTML = '<div class="integ-form-title">Account</div>'
        +'<div class="custom-panel">'
        +'<div class="custom-panel-note">Change password for '+_escapeHtml((CURRENT_USER||{{}}).username||'current user')+'. Requirements: minimum 8 characters, at least one uppercase, one lowercase, and one number OR symbol.</div>'
        +'<div id="form-grid" class="form-grid">'
        +'<div class="form-field span2"><label>Current Password</label><input id="acct-old" type="password" autocomplete="current-password"></div>'
        +'<div class="form-field"><label>New Password</label><input id="acct-new" type="password" autocomplete="new-password"></div>'
        +'<div class="form-field"><label>Confirm Password</label><input id="acct-confirm" type="password" autocomplete="new-password"></div>'
        +'</div><div class="form-actions"><button class="btn-save" onclick="changeOwnPassword()">&#10003; Change Password</button><span id="acct-msg" class="test-result" style="display:none"></span></div></div>';
      return;
    }}
    if (key === 'account_manage_users') {{
      if (!CURRENT_USER || CURRENT_USER.role !== 'admin') {{ right.innerHTML='<div class="settings-welcome">Admin role required.</div>'; return; }}
      right.innerHTML = '<div class="integ-form-title">Manage Users</div>'
        +'<div class="custom-panel"><div class="custom-panel-note">Create users, set role, reset passwords, or delete accounts. Password requirements: minimum 8 characters, at least one uppercase, one lowercase, and one number OR symbol.</div>'
        +'<div id="users-list">Loading&hellip;</div>'
        +'<div class="bcc-section-hdr">Create User</div><div id="form-grid" class="form-grid">'
        +'<div class="form-field"><label>Username</label><input id="new-user" autocomplete="off"></div>'
        +'<div class="form-field"><label>Role</label><select id="new-role"><option value="viewer">viewer</option><option value="admin">admin</option></select></div>'
        +'<div class="form-field"><label>Password</label><input id="new-pass" type="password"></div>'
        +'<div class="form-field"><label>Confirm</label><input id="new-confirm" type="password"></div>'
        +'</div><div class="form-actions"><button class="btn-save" onclick="createUser()">&#10003; Create User</button><span id="users-msg" class="test-result" style="display:none"></span></div></div>';
      loadUsers(); return;
    }}

    if (key === 'account_sessions') {{
      right.innerHTML = '<div class="integ-form-title">Active Sessions</div><div class="custom-panel"><div class="custom-panel-note">Current browser sessions. Revoke anything that smells wrong.</div><div id="sessions-list">Loading&hellip;</div></div>';
      loadSessions(); return;
    }}
    if (key === 'account_2fa') {{
      right.innerHTML = '<div class="integ-form-title">Two-Factor Auth</div><div class="custom-panel"><div class="custom-panel-note">TOTP support for Google Authenticator, Authy, 1Password, and anything else that can count to six.</div><div id="twofa-box">Loading&hellip;</div><div class="form-actions"><button class="btn-save" onclick="setup2FA()">Enable / Reconfigure 2FA</button><button class="report-action" onclick="disable2FA()">Disable 2FA</button><span id="twofa-msg" class="test-result" style="display:none"></span></div></div>';
      render2FA(); return;
    }}
    if (key === 'account_api_tokens') {{
      right.innerHTML = '<div class="integ-form-title">API Tokens</div><div class="custom-panel"><div class="custom-panel-note">Generate named API tokens for external integrations. The raw token is shown once.</div><div id="tokens-list">Loading&hellip;</div><div class="bcc-section-hdr">Create Token</div><div id="form-grid" class="form-grid"><div class="form-field"><label>Name</label><input id="token-name" value="Integration"></div><div class="form-field"><label>Expiry</label><select id="token-expiry"><option value="0">Never</option><option value="30">30 days</option><option value="60">60 days</option><option value="90">90 days</option><option value="180">180 days</option></select></div></div><div class="form-actions"><button class="btn-save" onclick="createApiToken()">Create Token</button><span id="token-msg" class="test-result" style="display:none"></span></div></div>';
      loadApiTokens(); return;
    }}
    if (key === 'account_login_history') {{
      right.innerHTML = '<div class="integ-form-title">Login History</div><div class="custom-panel"><div class="custom-panel-note">Last 100 login attempts with timestamp, IP, username, and result.</div><div id="login-history">Loading&hellip;</div></div>';
      loadLoginHistory(); return;
    }}
    if (key === 'account_password_expiry') {{
      right.innerHTML = '<div class="integ-form-title">Password Expiry</div><div class="custom-panel"><div class="custom-panel-note">Optional password expiry. Disabled by default, because mandatory rotation without cause is how auditors summon entropy demons.</div><div id="form-grid" class="form-grid"><div class="form-field span2"><label><input type="checkbox" id="expiry-enabled" style="width:16px;accent-color:var(--green)"> Enable password expiry</label></div><div class="form-field"><label>Expiry Period</label><select id="expiry-days"><option value="30">30 days</option><option value="60">60 days</option><option value="90">90 days</option><option value="180">180 days</option></select></div></div><div class="form-actions"><button class="btn-save" onclick="savePasswordExpiry()">Save</button><span id="expiry-msg" class="test-result" style="display:none"></span></div></div>';
      loadPasswordExpiry(); return;
    }}

    // General dashboard branding panel
    if (key === 'general_dashboard') {{
      var cfg = DASHBOARD_CONFIG || {{}};
      function _escAttr(v) {{ return String(v||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;'); }}
      right.innerHTML = '<div class="integ-form-title">General</div>'        +'<div class="custom-panel">'        +'<div class="custom-panel-note">Customize the top-bar branding. Saved to <code>state/config.json</code> and read on every regeneration.</div>'        +'<div id="form-grid" class="form-grid">'        +'<div class="form-field span2"><label>Dashboard Title</label>'        +'<input id="field-dashboard_title" type="text" value="'+_escAttr(cfg.dashboard_title||'NOC Dashboard')+'" data-key="dashboard_title" autocomplete="off"></div>'        +'<div class="form-field span2"><label>Subtitle</label>'        +'<input id="field-dashboard_subtitle" type="text" value="'+_escAttr(cfg.dashboard_subtitle||'Infrastructure Monitoring')+'" data-key="dashboard_subtitle" autocomplete="off"></div>'        +'<div class="form-field span2"><label>Logo URL (optional)</label>'        +'<input id="field-logo_url" type="text" value="'+_escAttr(cfg.logo_url||'')+'" placeholder="https://example.com/logo.png" data-key="logo_url" autocomplete="off"></div>'        +'<div class="form-field span2" style="align-items:center;display:flex;gap:10px;padding:6px 0">'        +'<label style="margin:0;font-size:12px;letter-spacing:1px;cursor:pointer;display:flex;align-items:center;gap:8px">'        +'<input type="checkbox" id="field-show_ticker_bar" '+(cfg.show_ticker_bar!==false?'checked':'')+' style="width:14px;height:14px;cursor:pointer;accent-color:var(--green)">'        +'Show ticker bar (scrolling alert strip)</label>'        +'</div>'        +'</div><div class="form-actions">'        +'<button class="btn-save" id="btn-save" onclick="saveDashboardConfig()">&#10003; Save &amp; Apply</button>'        +'<span id="test-result" class="test-result" style="display:none"></span>'        +'</div></div>';
      return;
    }}

    // Date & Time settings panel
    if (key === 'datetime_settings') {{
      var cfg = DASHBOARD_CONFIG || {{}};
      var tzOpts = ['UTC','America/New_York','America/Chicago','America/Denver','America/Los_Angeles','America/Phoenix','Europe/London','Europe/Berlin','Europe/Paris','Europe/Madrid','Asia/Tokyo','Asia/Shanghai','Asia/Singapore','Asia/Kolkata','Australia/Sydney','Australia/Melbourne','Pacific/Auckland'].map(function(tz){{return '<option value="'+tz+'" '+((cfg.timezone||'UTC')===tz?'selected':'')+'>'+tz+'</option>';}}).join('');
      var dfOpts = ['YYYY-MM-DD','MM/DD/YYYY','DD/MM/YYYY'].map(function(f){{return '<option value="'+f+'" '+((cfg.date_format||'YYYY-MM-DD')===f?'selected':'')+'>'+f+'</option>';}}).join('');
      right.innerHTML = '<div class="integ-form-title">&#128197; Date &amp; Time</div>'
        +'<div class="custom-panel">'
        +'<div class="custom-panel-note">All timestamps on the dashboard respect these settings. Changes take effect on the next regeneration.</div>'
        +'<div id="form-grid" class="form-grid">'
        +'<div class="form-field span2"><label>Time Zone</label>'
        +'<select id="dt-timezone">'+tzOpts+'</select></div>'
        +'<div class="form-field span2"><label>Date Format</label>'
        +'<select id="dt-date-format">'+dfOpts+'</select></div>'
        +'<div class="form-field span2"><label>Clock Format</label>'
        +'<div style="display:flex;gap:16px;align-items:center;margin-top:4px">'
        +'<label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;letter-spacing:1px">'
        +'<input type="radio" name="clock-fmt" id="dt-clock-12" value="12hr" style="accent-color:var(--green)" '+((cfg.clock_format||'24hr')==='12hr'?'checked':'')+'>12-hour (1:30 PM)</label>'
        +'<label style="display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;letter-spacing:1px">'
        +'<input type="radio" name="clock-fmt" id="dt-clock-24" value="24hr" style="accent-color:var(--green)" '+((cfg.clock_format||'24hr')==='24hr'?'checked':'')+'>24-hour (13:30)</label>'
        +'</div></div>'
        +'</div>'
        +'<div class="form-actions">'
        +'<button class="btn-save" id="btn-save" onclick="saveDateTimeConfig()">&#10003; Save &amp; Apply</button>'
        +'<span id="test-result" class="test-result" style="display:none"></span>'
        +'</div></div>';
      return;
    }}

    // Reports panel
    if (key === 'reports') {{
      right.innerHTML = '<div class="integ-form-title">Reports</div>'
        +'<div class="custom-panel">'
        +'<div class="custom-panel-note">Generate dashboard reports from the current rendered card state and recorded alert history.</div>'
        +'<div class="report-tabs">'
        +'<button class="report-tab active" data-range="daily" onclick="renderSettingsReport(&quot;daily&quot;)">Daily</button>'
        +'<button class="report-tab" data-range="weekly" onclick="renderSettingsReport(&quot;weekly&quot;)">Weekly</button>'
        +'<button class="report-tab" data-range="monthly" onclick="renderSettingsReport(&quot;monthly&quot;)">Monthly</button>'
        +'</div>'
        +'<div class="report-actions">'
        +'<button class="report-action" onclick="downloadReportCSV()">Download</button>'
        +'<button class="report-action" onclick="downloadReportPDF()">Export</button>'
        +'</div>'
        +'<div id="settings-report-summary" class="report-summary"></div>'
        +'</div>';
      renderSettingsReport('daily');
      return;
    }}

    // Alert ticker toggle panel
    if (key === 'toggle_alerts') {{
      var tickerVisible = (DASHBOARD_CONFIG || {{}}).show_ticker_bar !== false;
      try {{ var storedTicker = localStorage.getItem(TICKER_PREF_KEY); if (storedTicker !== null) tickerVisible = storedTicker === '1'; }} catch(e) {{}}
      right.innerHTML = '<div class="integ-form-title">Toggle Alerts</div>'
        +'<div class="custom-panel">'
        +'<div class="custom-panel-note">Show or hide the scrolling alert ticker bar. This uses the same dashboard preference as the old top-bar toggle.</div>'
        +'<label style="display:flex;align-items:center;gap:10px;font-size:12px;letter-spacing:1px;cursor:pointer">'
        +'<input type="checkbox" id="settings-toggle-alerts" '+(tickerVisible?'checked':'')+' style="width:16px;height:16px;accent-color:var(--green);cursor:pointer" onchange="setTickerVisibility(this.checked)">'
        +'Show ticker bar</label>'
        +'</div>';
      return;
    }}

    // Custom integration panel
    if (key === 'custom') {{
      right.innerHTML = '<div class="integ-form-title">&#10010; Custom Integration</div>'\
        +'<div class="custom-panel">'\
        +'<div class="custom-panel-note">Define your own integration: name, URL, auth type, and a JSONPath to extract a status value. The collector will make a periodic HTTP request and surface the result as a card.</div>'\
        +'<div id="form-grid" class="form-grid">'\
        +'<div class="form-field span2"><label>Integration Name</label>'\
        +'<input id="field-CUSTOM_NAME" type="text" placeholder="My Service" data-key="CUSTOM_NAME" autocomplete="off"></div>'\
        +'<div class="form-field span2"><label>URL</label>'\
        +'<input id="field-CUSTOM_URL" type="text" placeholder="http://host:port/api/status" data-key="CUSTOM_URL" autocomplete="off"></div>'\
        +'<div class="form-field"><label>Auth Type</label>'\
        +'<select id="field-CUSTOM_AUTH" data-key="CUSTOM_AUTH" style="background:var(--panel);border:1px solid var(--line);color:var(--txt);padding:6px 10px;border-radius:4px;font-size:12px;font-family:inherit">'\
        +'<option value="none">None</option>'\
        +'<option value="bearer">Bearer Token</option>'\
        +'<option value="basic">Basic Auth (user:pass)</option>'\
        +'<option value="apikey">API Key Header</option>'\
        +'</select></div>'\
        +'<div class="form-field"><label>Auth Value</label>'\
        +'<input id="field-CUSTOM_AUTH_VALUE" type="password" placeholder="token or user:pass" data-key="CUSTOM_AUTH_VALUE" autocomplete="off"></div>'\
        +'<div class="form-field span2"><label>JSONPath (optional)</label>'\
        +'<input id="field-CUSTOM_JSONPATH" type="text" placeholder=".status or .data.health" data-key="CUSTOM_JSONPATH" autocomplete="off"></div>'\
        +'</div>'\
        +'<div class="form-actions">'\
        +'<button class="btn-save" id="btn-save" onclick="saveConfig()">&#10003; Save &amp; Apply</button>'\
        +'<span id="test-result" class="test-result" style="display:none"></span>'\
        +'</div></div>';\
      return;
    }}

    var integ = _integByKey(key);
    if (!integ) return;
    var sc = _stateColor(integ.state);
    var isComingSoon = integ.state === 'coming_soon';
    var statusLabel = isComingSoon?'READY — credentials can be stored now'
      :integ.state==='ok'?'&#10003; Connected'\
      :integ.state==='warn'?'&#9888; Warning'\
      :integ.state==='degraded'?'&#8212; Not Configured':'&#10005; Error';
    var statusColor = isComingSoon?'var(--green)'
      :integ.state==='ok'?'var(--green)':integ.state==='warn'?'var(--warn)'\
      :integ.state==='degraded'?'var(--degr)':'var(--crit)';
    right.innerHTML = '<div class="integ-form-title">'+(isComingSoon?'&#9899; ':'')+integ.label+'</div>'\
      +(isComingSoon?'<div class="badge-soon" style="display:inline-block;margin-bottom:10px">READY</div>':'')\
      +'<div class="integ-form-status" style="color:'+statusColor+';border-color:'+statusColor+'">'\
      +'<span class="sidebar-dot '+sc+'"></span>&nbsp;'+statusLabel\
      +(integ.note?' &mdash; <span style="font-weight:normal;text-transform:none;color:var(--muted)">'+integ.note+'</span>':'')\
      +'</div>'\
      +(isComingSoon?'<div class="coming-soon-msg">Collector not connected. Store credentials now \u2014 integration will activate when a collector is added.</div>':'')\
      +'<div id="form-grid" class="form-grid"><div style="color:var(--muted);font-size:11px">Loading&hellip;</div></div>'\
      +'<div class="form-actions">'\
      +'<button class="btn-test" id="btn-test" onclick="testConnection()">&#9654; Test Connection</button>'\
      +'<button class="btn-save" id="btn-save" onclick="saveConfig()">&#10003; Save &amp; Apply</button>'\
      +'<span id="test-result" class="test-result" style="display:none"></span>'\
      +'</div>';
    _loadFieldDefs(function(defs) {{
      _loadCurrentCfg(function(cfg) {{
        var fields = _fieldsFor(defs, key);
        var fg = document.getElementById('form-grid');
        if (!fg) return;
        if (!fields.length) {{
          fg.innerHTML='<div style="color:var(--muted);font-size:11px;padding:8px">No configurable fields.</div>';
          return;
        }}
        fg.innerHTML = fields.map(function(f) {{
          var isSet = cfg[f.key] && cfg[f.key]!=='&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;';
          var ph = f.type==='password'?(isSet?'(set \u2014 enter new to change)':'enter password'):(f.label||f.key);
          return '<div class="form-field">'\
            +'<label for="field-'+f.key+'">'+(f.label||f.key)+'</label>'\
            +'<input id="field-'+f.key+'" type="'+f.type+'" placeholder="'+ph+'" '\
            +'autocomplete="off" data-key="'+f.key+'">'\
            +'</div>';
        }}).join('');
      }});
    }});
  }}

  function _getFormValues() {{
    var vals = {{}};
    document.querySelectorAll('#form-grid input[data-key], #form-grid select[data-key]').forEach(function(inp){{
      if (inp.value.trim()) vals[inp.dataset.key]=inp.value.trim();
    }});
    return vals;
  }}

  window.testConnection = function() {{
    if (!_selectedType) return;
    var btn=document.getElementById('btn-test'), tr=document.getElementById('test-result');
    if (!btn||!tr) return;
    btn.disabled=true; tr.style.display='inline-block';
    tr.className='test-result testing'; tr.textContent='⧙ Testing…';
    fetch('/test-connection',{{method:'POST',headers:{{'Content-Type':'application/json'}},
      body:JSON.stringify({{type:_selectedType,creds:_getFormValues()}})}})
    .then(function(r){{return r.json();}})
    .then(function(d){{
      btn.disabled=false;
      tr.className='test-result '+(d.ok?'ok':'error');
      if (d.ok) {{
        var detail=Object.entries(d.detail||{{}}).slice(0,4)
          .map(function(e){{return e[0].replace(/_/g,' ')+': '+e[1];}}).join(' · ');
        tr.textContent='✓ Connected'+(detail?' — '+detail:'');
      }} else {{ tr.textContent='✕ '+(d.note||d.error||'Connection failed'); }}
    }})
    .catch(function(e){{btn.disabled=false;tr.className='test-result error';tr.textContent='✕ '+e.message;}});
  }};

  window.saveDashboardConfig = function() {{
    var tickerCb = document.getElementById('field-show_ticker_bar');
    var vals = {{
      dashboard_title: (document.getElementById('field-dashboard_title')||{{value:''}}).value.trim(),
      dashboard_subtitle: (document.getElementById('field-dashboard_subtitle')||{{value:''}}).value.trim(),
      logo_url: (document.getElementById('field-logo_url')||{{value:''}}).value.trim(),
      timezone: (document.getElementById('field-timezone')||{{value:'UTC'}}).value.trim() || 'UTC',
      show_ticker_bar: tickerCb ? tickerCb.checked : true
    }};
    var btn=document.getElementById('btn-save'), tr=document.getElementById('test-result');
    if (btn) {{ btn.disabled=true; btn.textContent='⧙ Saving…'; }}
    fetch('/save-dashboard-config',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(vals)}})
    .then(function(r){{return r.json();}})
    .then(function(d){{
      if (btn) {{ btn.disabled=false; btn.textContent='✓ Save & Apply'; }}
      DASHBOARD_CONFIG=d.config||vals;
      // Apply ticker preference immediately
      _applyTickerPref(vals.show_ticker_bar);
      localStorage.setItem(TICKER_PREF_KEY, vals.show_ticker_bar ? '1' : '0');
      if (tr){{tr.style.display='inline-block';tr.className='test-result ok';tr.textContent='✓ Saved — regen started';}}
    }})
    .catch(function(e){{if(btn){{btn.disabled=false;btn.textContent='✓ Save & Apply';}} alert('Save failed: '+e.message);}});
  }};

  window.saveDateTimeConfig = function() {{
    var tz = (document.getElementById('dt-timezone')||{{}}).value || 'UTC';
    var df = (document.getElementById('dt-date-format')||{{}}).value || 'YYYY-MM-DD';
    var clkEl = document.querySelector('input[name="clock-fmt"]:checked');
    var clk = clkEl ? clkEl.value : '24hr';
    var vals = Object.assign({{}}, DASHBOARD_CONFIG || {{}}, {{
      timezone: tz,
      date_format: df,
      clock_format: clk
    }});
    var btn = document.getElementById('btn-save'), tr = document.getElementById('test-result');
    if (btn) {{ btn.disabled=true; btn.textContent='⧙ Saving…'; }}
    fetch('/save-dashboard-config',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(vals)}})
    .then(function(r){{return r.json();}})
    .then(function(d){{
      if (btn) {{ btn.disabled=false; btn.textContent='✓ Save & Apply'; }}
      DASHBOARD_CONFIG = d.config || vals;
      if (tr){{tr.style.display='inline-block';tr.className='test-result ok';tr.textContent='✓ Saved — regen started';}}
    }})
    .catch(function(e){{if(btn){{btn.disabled=false;btn.textContent='✓ Save & Apply';}} alert('Save failed: '+e.message);}});
  }};

  window.saveConfig = function() {{
    if (!_selectedType) return;
    var vals=_getFormValues();
    if (!Object.keys(vals).length){{alert('No values entered.');return;}}
    var btn=document.getElementById('btn-save'), tr=document.getElementById('test-result');
    if (!btn) return;
    btn.disabled=true; btn.textContent='⧙ Saving…';
    fetch('/save-config',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(vals)}})
    .then(function(r){{return r.json();}})
    .then(function(d){{
      btn.disabled=false; btn.textContent='✓ Save & Apply'; _currentCfg=null;
      if (tr){{tr.style.display='inline-block';tr.className='test-result ok';tr.textContent='✓ Saved — regen started';}}
    }})
    .catch(function(e){{btn.disabled=false;btn.textContent='✓ Save & Apply';alert('Save failed: '+e.message);}});
  }};

  window.toggleSettings = function() {{
    var ov=document.getElementById('settings-overlay');
    var isOpen=ov.classList.toggle('open');
    if (isOpen) {{
      buildSidebar();
      loadAuthStatus(function(){{ buildSidebar(); }}); document.body.style.overflow='hidden';
      _selectedType=null;
      var right=document.getElementById('settings-right');
      if (right) right.innerHTML='<div class="settings-welcome">'
        +'<span class="settings-welcome-icon">&#9881;</span>'
        +'Select Account or an integration from the sidebar.</div>';
    }} else {{ document.body.style.overflow=''; }}
  }};

  window.settingsOverlayClick = function(e) {{
    var ov=document.getElementById('settings-overlay');
    var shell=document.querySelector('.settings-shell');
    if (!e || !ov || e.target !== ov) return;
    if (e.clientX >= document.documentElement.clientWidth || e.clientY >= document.documentElement.clientHeight) return;
    var path=e.composedPath?e.composedPath():[];
    if (shell && (shell.contains(e.target) || path.indexOf(shell)!==-1)) return;
    window.toggleSettings();
  }};

  document.addEventListener('keydown', function(e) {{
    if (e.key==='Escape') {{
      var ov=document.getElementById('settings-overlay');
      if (ov&&ov.classList.contains('open')){{window.toggleSettings();return;}}
    }}
  }});

  function loadAuthStatus(cb) {{
    fetch('/api/auth-status').then(function(r){{ if(r.status===401){{ location.href='/login'; return null; }} return r.json(); }})
      .then(function(d){{ if(!d) return; CURRENT_USER=d.user||null; applyRoleUI(); if(CURRENT_USER&&CURRENT_USER.password_expired){{setTimeout(function(){{ alert('Your password has expired. Change it now.'); var ov=document.getElementById('settings-overlay'); if(!(ov&&ov.classList.contains('open'))) window.toggleSettings(); selectInteg('account_change_password'); }},500);}} else if(CURRENT_USER&&CURRENT_USER.password_warning_days!==null&&CURRENT_USER.password_warning_days!==undefined){{setTimeout(function(){{ alert('Password expires in '+CURRENT_USER.password_warning_days+' day(s).'); }},500);}} if(cb) cb(d); }})
      .catch(function(){{ if(cb) cb(null); }});
  }}
  function applyRoleUI() {{
    var isViewer = CURRENT_USER && CURRENT_USER.role === 'viewer';
    document.body.classList.toggle('viewer-role', !!isViewer);
    var old=document.getElementById('auth-user-menu');
    if(old) old.remove();
    var username = (CURRENT_USER && CURRENT_USER.username) || 'user';
    var role = (CURRENT_USER && CURRENT_USER.role) || 'viewer';
    var nameEl=document.getElementById('gear-user-name');
    var roleEl=document.getElementById('gear-user-role');
    if(nameEl) nameEl.textContent=username;
    if(roleEl) roleEl.textContent=role;
  }}
  var _adminToggleEditMode = window.toggleEditMode;
  window.toggleEditMode = function() {{
    if (CURRENT_USER && CURRENT_USER.role !== 'admin') return;
    return _adminToggleEditMode.apply(this, arguments);
  }};
  var _adminCancelEditMode = window.cancelEditMode;
  window.cancelEditMode = function() {{
    if (CURRENT_USER && CURRENT_USER.role !== 'admin') return;
    return _adminCancelEditMode.apply(this, arguments);
  }};
  window.toggleGearMenu = function(open) {{ var m=document.getElementById('gear-menu'); if(!m)return; var show=(open===undefined||open&&open.type)?!m.classList.contains('open'):!!open; m.classList.toggle('open',show); }};
  document.addEventListener('click', function(e) {{ var gm=document.getElementById('gear-menu'); if(gm&&!gm.contains(e.target)) gm.classList.remove('open'); }});
  document.addEventListener('keydown', function(e) {{ if(e.key==='Escape'){{ var gm=document.getElementById('gear-menu'); if(gm)gm.classList.remove('open'); }} }});
  window.logoutUser = function() {{ fetch('/api/logout',{{method:'POST'}}).then(function(){{ location.href='/login'; }}); }};
  function _acctMsg(id, ok, msg) {{ var el=document.getElementById(id); if(el){{el.style.display='inline-block';el.className='test-result '+(ok?'ok':'error');el.textContent=msg;}} }}
  window.changeOwnPassword = function() {{
    var payload={{old_password:(document.getElementById('acct-old')||{{}}).value||'',new_password:(document.getElementById('acct-new')||{{}}).value||'',confirm_password:(document.getElementById('acct-confirm')||{{}}).value||''}};
    fetch('/api/change-password',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}})
      .then(function(r){{return r.json().then(function(d){{return {{ok:r.ok,d:d}};}});}})
      .then(function(x){{_acctMsg('acct-msg',x.ok&&x.d.ok,x.ok&&x.d.ok?'✓ Password changed':(x.d.error||'Password change failed'));}});
  }};
  window.loadUsers = function() {{
    fetch('/api/users',{{method:'POST'}}).then(function(r){{return r.json();}}).then(function(d){{
      var el=document.getElementById('users-list'); if(!el) return;
      var rows=(d.users||[]).map(function(u){{return '<tr><td>'+_escapeHtml(u.username)+(u.locked?' <span class="badge-soon">LOCKED</span>':'')+(u.totp_enabled?' <span class="badge-soon">2FA</span>':'')+'</td><td>'+_escapeHtml(u.role)+'</td><td><button class="report-action" onclick="resetUserPassword(&quot;'+_escapeHtml(u.username)+'&quot;)">Reset Password</button> <button class="report-action" onclick="unlockUser(&quot;'+_escapeHtml(u.username)+'&quot;)">Unlock</button> <button class="report-action" onclick="resetUser2FA(&quot;'+_escapeHtml(u.username)+'&quot;)">Reset 2FA</button> <button class="report-action" onclick="deleteUser(&quot;'+_escapeHtml(u.username)+'&quot;)">Delete</button></td></tr>';}}).join('');
      el.innerHTML='<table class="user-table"><thead><tr><th>User</th><th>Role</th><th>Actions</th></tr></thead><tbody>'+rows+'</tbody></table>';
    }});
  }};
  window.createUser = function() {{
    var p=(document.getElementById('new-pass')||{{}}).value||'', c=(document.getElementById('new-confirm')||{{}}).value||'';
    if(p!==c){{_acctMsg('users-msg',false,'Passwords do not match.');return;}}
    var payload={{username:(document.getElementById('new-user')||{{}}).value||'',role:(document.getElementById('new-role')||{{}}).value||'viewer',password:p}};
    fetch('/api/users/create',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}})
      .then(function(r){{return r.json().then(function(d){{return {{ok:r.ok,d:d}};}});}})
      .then(function(x){{_acctMsg('users-msg',x.ok&&x.d.ok,x.ok&&x.d.ok?'✓ User created':(x.d.error||'Create failed')); if(x.ok&&x.d.ok)loadUsers();}});
  }};
  window.resetUserPassword = function(username) {{
    var p=prompt('New password for '+username+' (min 8, upper, lower, number OR symbol):'); if(!p) return;
    fetch('/api/users/reset-password',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{username:username,password:p}})}})
      .then(function(r){{return r.json().then(function(d){{return {{ok:r.ok,d:d}};}});}})
      .then(function(x){{_acctMsg('users-msg',x.ok&&x.d.ok,x.ok&&x.d.ok?'✓ Password reset':(x.d.error||'Reset failed'));}});
  }};
  window.deleteUser = function(username) {{
    if(!confirm('Delete user '+username+'?')) return;
    fetch('/api/users/delete',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{username:username}})}})
      .then(function(r){{return r.json().then(function(d){{return {{ok:r.ok,d:d}};}});}})
      .then(function(x){{_acctMsg('users-msg',x.ok&&x.d.ok,x.ok&&x.d.ok?'✓ User deleted':(x.d.error||'Delete failed')); if(x.ok&&x.d.ok)loadUsers();}});
  }};
  function fmtTime(ts) {{ if(!ts) return '—'; try {{ return new Date(ts*1000).toLocaleString(); }} catch(e) {{ return String(ts); }} }}
  window.loadSessions = function() {{ fetch('/api/sessions',{{method:'POST'}}).then(function(r){{return r.json();}}).then(function(d){{ var el=document.getElementById('sessions-list'); if(!el)return; var rows=(d.sessions||[]).map(function(s){{return '<tr><td>'+_escapeHtml(s.username||'')+(s.current?' <span class="badge-soon">CURRENT</span>':'')+'</td><td>'+_escapeHtml(s.ip||'')+'</td><td>'+fmtTime(s.last_activity)+'</td><td>'+_escapeHtml((s.user_agent||'').slice(0,80))+'</td><td><button class="report-action" onclick="revokeSession(&quot;'+_escapeHtml(s.id)+'&quot;)">Revoke</button></td></tr>';}}).join(''); el.innerHTML='<table class="user-table"><thead><tr><th>User</th><th>IP</th><th>Last Activity</th><th>Browser</th><th></th></tr></thead><tbody>'+rows+'</tbody></table>'; }}); }};
  window.revokeSession = function(id) {{ fetch('/api/sessions/revoke',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:id}})}}).then(function(){{loadSessions();}}); }};
  window.render2FA = function() {{ var el=document.getElementById('twofa-box'); if(el) el.innerHTML='<div>2FA status: '+((CURRENT_USER&&CURRENT_USER.totp_enabled)?'enabled':'disabled')+'</div>'; }};
  window.setup2FA = function() {{ fetch('/api/2fa/setup',{{method:'POST'}}).then(function(r){{return r.json();}}).then(function(d){{ var el=document.getElementById('twofa-box'); if(!el)return; el.innerHTML='<div style="display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap"><img alt="TOTP QR" src="'+d.qr_url+'" style="background:#fff;padding:8px;border-radius:4px"><div><div class="custom-panel-note">Scan the QR code, or enter this key manually:</div><code>'+_escapeHtml(d.secret)+'</code><div class="form-field"><label>Confirmation Code</label><input id="twofa-code" inputmode="numeric" autocomplete="one-time-code"></div><button class="btn-save" onclick="enable2FA()">Confirm & Enable</button></div></div>'; }}); }};
  window.enable2FA = function() {{ fetch('/api/2fa/enable',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{code:(document.getElementById('twofa-code')||{{}}).value||''}})}}).then(function(r){{return r.json().then(function(d){{return {{ok:r.ok,d:d}};}});}}).then(function(x){{_acctMsg('twofa-msg',x.ok&&x.d.ok,x.ok&&x.d.ok?'✓ 2FA enabled':(x.d.error||'Enable failed')); loadAuthStatus(render2FA);}}); }};
  window.disable2FA = function() {{ var p=prompt('Current password to disable 2FA:'); if(!p)return; fetch('/api/2fa/disable',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{password:p}})}}).then(function(r){{return r.json().then(function(d){{return {{ok:r.ok,d:d}};}});}}).then(function(x){{_acctMsg('twofa-msg',x.ok&&x.d.ok,x.ok&&x.d.ok?'✓ 2FA disabled':(x.d.error||'Disable failed')); loadAuthStatus(render2FA);}}); }};
  window.loadApiTokens = function() {{ fetch('/api/api-tokens',{{method:'POST'}}).then(function(r){{return r.json();}}).then(function(d){{ var el=document.getElementById('tokens-list'); if(!el)return; var rows=(d.tokens||[]).map(function(t){{return '<tr><td>'+_escapeHtml(t.name||'')+'</td><td>'+fmtTime(t.created)+'</td><td>'+(t.expires?fmtTime(t.expires):'Never')+'</td><td><button class="report-action" onclick="revokeApiToken(&quot;'+_escapeHtml(t.id)+'&quot;)">Revoke</button></td></tr>';}}).join(''); el.innerHTML='<table class="user-table"><thead><tr><th>Name</th><th>Created</th><th>Expires</th><th></th></tr></thead><tbody>'+rows+'</tbody></table>'; }}); }};
  window.createApiToken = function() {{ fetch('/api/api-tokens/create',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name:(document.getElementById('token-name')||{{}}).value||'Integration',expiry_days:parseInt((document.getElementById('token-expiry')||{{}}).value||'0',10)}})}}).then(function(r){{return r.json();}}).then(function(d){{_acctMsg('token-msg',!!d.ok,d.ok?'Token: '+d.token:(d.error||'Create failed')); loadApiTokens();}}); }};
  window.revokeApiToken = function(id) {{ fetch('/api/api-tokens/revoke',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{id:id}})}}).then(function(){{loadApiTokens();}}); }};
  window.loadLoginHistory = function() {{ fetch('/api/login-history',{{method:'POST'}}).then(function(r){{return r.json();}}).then(function(d){{ var el=document.getElementById('login-history'); if(!el)return; var rows=(d.entries||[]).map(function(e){{return '<tr><td>'+fmtTime(e.ts)+'</td><td>'+_escapeHtml(e.ip||'')+'</td><td>'+_escapeHtml(e.username||'')+'</td><td>'+(e.success?'OK':'FAIL')+'</td><td>'+_escapeHtml(e.reason||'')+'</td></tr>';}}).join(''); el.innerHTML='<table class="user-table"><thead><tr><th>Time</th><th>IP</th><th>User</th><th>Result</th><th>Reason</th></tr></thead><tbody>'+rows+'</tbody></table>'; }}); }};
  window.loadPasswordExpiry = function() {{ fetch('/api/security-settings',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{}})}}).then(function(r){{return r.json();}}).then(function(d){{ var s=d.settings||{{}}; var e=document.getElementById('expiry-enabled'), days=document.getElementById('expiry-days'); if(e)e.checked=!!s.password_expiry_enabled; if(days)days.value=String(s.password_expiry_days||90); }}); }};
  window.savePasswordExpiry = function() {{ var payload={{password_expiry_enabled:!!(document.getElementById('expiry-enabled')||{{}}).checked,password_expiry_days:parseInt((document.getElementById('expiry-days')||{{}}).value||'90',10)}}; fetch('/api/security-settings',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(payload)}}).then(function(r){{return r.json();}}).then(function(d){{_acctMsg('expiry-msg',!!d.ok,d.ok?'✓ Saved':(d.error||'Save failed'));}}); }};
  window.unlockUser = function(username) {{ fetch('/api/users/unlock',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{username:username}})}}).then(function(){{loadUsers();}}); }};
  window.resetUser2FA = function(username) {{ if(!confirm('Reset 2FA for '+username+'?')) return; fetch('/api/users/reset-2fa',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{username:username}})}}).then(function(){{loadUsers();}}); }};
  loadAuthStatus();

  /* ── Welcome screen ── */
  var WELCOME_KEY = 'noc-welcomed';
  window.welcomeSkip = function() {{
    localStorage.setItem(WELCOME_KEY, '1');
    var ov = document.getElementById('welcome-overlay');
    if (ov) ov.classList.remove('open');
  }};
  window.welcomeOpenSettings = function() {{
    welcomeSkip();
    window.toggleSettings();
  }};
  window.openSetupWizard = function() {{
    var ov = document.getElementById('welcome-overlay');
    if (ov) ov.classList.add('open');
    // Close settings if open
    var sov = document.getElementById('settings-overlay');
    if (sov && sov.classList.contains('open')) window.toggleSettings();
  }};
  (function() {{
    if (!localStorage.getItem(WELCOME_KEY)) {{
      var ov = document.getElementById('welcome-overlay');
      if (ov) ov.classList.add('open');
    }}
  }})();
}})();
{intel_js}
{cc_js}
</script>
</body></html>"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    gen_epoch = time.time()
    data = gather()
    errors = {k: v.get("error") for k, v in data.items() if v.get("state") == "error"}
    try:
        health_summary = build_health_summary(data, gen_epoch)
        record_health_snapshot(health_summary)
    except Exception as e:
        health_summary = build_health_summary(data, gen_epoch)
        print(f"warn: health snapshot failed: {type(e).__name__}: {str(e)[:80]}")
    try:
        trends = update_trends(data, gen_epoch)
    except Exception as e:
        trends = load_trends()
        print(f"warn: trend update failed: {type(e).__name__}: {str(e)[:80]}")
    page = render(data, gen_epoch, errors, trends, health_summary)
    tmp = OUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, OUT_FILE)  # atomic - server never serves a half-written file
    ok = sum(1 for v in data.values() if v.get("state") == "ok")
    print(f"dashboard written: {OUT_FILE} ({len(page):,} bytes) | "
          f"{ok}/{len(data)} sources green | errors: {list(errors) or 'none'}")


if __name__ == "__main__":
    main()
