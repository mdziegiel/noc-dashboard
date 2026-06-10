#!/usr/bin/env python3
"""
NOC Dashboard — FastAPI backend server
Wraps existing collectors, serves JSON API + React frontend static files.

Endpoints:
  GET  /api/card-types            list of known card types with metadata
  GET  /api/data/{card_type}      run collector, return live data as JSON
  GET  /api/themes                all themes as CSS variable maps
  GET  /api/layout                current layout.json
  POST /api/layout                save layout.json
  GET  /api/config                dashboard.yaml top-level config
  GET  /api/ticker                aggregated alerts/stats for scrolling ticker
  GET  /api/status-overview       counts of ok/warn/crit across all cards
  GET  /api/events                SSE stream for live card updates
  GET  /                          React app (served from frontend/dist/)

Usage:
    uvicorn server:app --host 0.0.0.0 --port 8081
"""

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import traceback
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed.", file=sys.stderr)
    sys.exit(1)

try:
    import bcrypt
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
except ImportError:
    print("ERROR: fastapi not installed. Run: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

# ── Project root ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "trends.json"
THEMES_DIR = ROOT / "themes"
FRONTEND_DIST = ROOT / "frontend" / "dist"
LAYOUT_FILE = STATE_DIR / "layout.json"
CONFIG_FILE = ROOT / (os.environ.get("CONFIG_FILE") or "dashboard.yaml")
ENV_FILE = ROOT / ".env"
CONFIG_JSON = STATE_DIR / "config.json"
DB_FILE = STATE_DIR / "noc_dashboard.sqlite3"
SESSION_COOKIE = "noc_session"
SESSION_TTL_SECONDS = 90 * 24 * 3600

# ── Env loader ─────────────────────────────────────────────────────────────────

def load_env(path):
    d = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r'^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)$', line.rstrip("\n"))
                if m:
                    d[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    for k, v in os.environ.items():
        if k in d or k.isupper():
            d[k] = v
    return d


E = load_env(ENV_FILE)
# Note: E is patched at startup (after CONFIG_JSON is defined) and on each integration save.
# See _apply_config_json_to_E() called after CONFIG_JSON is defined below.


# ── Authentication ─────────────────────────────────────────────────────────────

def _now() -> int:
    return int(time.time())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _get_admin(cfg_json: dict) -> dict | None:
    admin = cfg_json.get("admin")
    if isinstance(admin, dict) and admin.get("username") and admin.get("password_hash"):
        return admin
    return None


def _create_session(cfg_json: dict) -> str:
    token = secrets.token_urlsafe(48)
    sessions = cfg_json.setdefault("sessions", {})
    sessions[_hash_token(token)] = {"created": _now(), "expires": _now() + SESSION_TTL_SECONDS}
    # Prune expired sessions. State files should not become a landfill.
    for key, sess in list(sessions.items()):
        if int(sess.get("expires", 0)) < _now():
            sessions.pop(key, None)
    save_config_json(cfg_json)
    return token


def _verify_session_token(cfg_json: dict, token: str | None) -> bool:
    if not token or not _get_admin(cfg_json):
        return False
    sessions = cfg_json.get("sessions", {})
    token_hash = _hash_token(token)
    sess = sessions.get(token_hash)
    if not sess:
        return False
    if int(sess.get("expires", 0)) < _now():
        sessions.pop(token_hash, None)
        save_config_json(cfg_json)
        return False
    return True


def _clear_session_token(cfg_json: dict, token: str | None):
    if token:
        cfg_json.get("sessions", {}).pop(_hash_token(token), None)
        save_config_json(cfg_json)


def _password_ok(password: str) -> bool:
    return isinstance(password, str) and len(password) >= 8


def _auth_response(payload: dict, token: str | None = None, remember: bool = True):
    resp = JSONResponse(payload)
    if token:
        cookie_args = {
            "key": SESSION_COOKIE,
            "value": token,
            "httponly": True,
            "samesite": "lax",
            "path": "/",
        }
        if remember:
            cookie_args["max_age"] = SESSION_TTL_SECONDS
        resp.set_cookie(**cookie_args)
    return resp

# ── Theme loader ───────────────────────────────────────────────────────────────

THEME_DEFAULTS = {
    "background": "#0a0a0a",
    "card_background": "#111111",
    "card_border": "#1e1e1e",
    "accent": "#00ff41",
    "accent_secondary": "#00cc33",
    "text_primary": "#e0e0e0",
    "text_secondary": "#a0a0a0",
    "text_muted": "#555555",
    "ok_color": "#00ff41",
    "warn_color": "#ffaa00",
    "error_color": "#ff3333",
    "critical_color": "#ff0000",
    "font_family": "JetBrains Mono, Fira Code, Consolas, monospace",
    "font_size_base": "13px",
    "heading_font": "JetBrains Mono, Fira Code, monospace",
    "card_border_radius": "4px",
    "card_shadow": "0 0 8px rgba(0,255,65,0.08)",
    "section_header_color": "#00ff41",
    "graph_line_color": "#00ff41",
    "graph_fill_color": "rgba(0,255,65,0.12)",
    "gauge_track_color": "#1a1a1a",
    "gauge_fill_ok": "#00ff41",
    "gauge_fill_warn": "#ffaa00",
    "gauge_fill_critical": "#ff3333",
    "sparkline_stroke_width": "2",
    "top_bar_background": "#000000",
    "top_bar_border": "#1a1a1a",
}


def load_all_themes():
    themes = {}
    for f in THEMES_DIR.glob("*.yaml"):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh) or {}
            merged = dict(THEME_DEFAULTS)
            merged.update({k: v for k, v in data.items() if k not in ("name", "description")})
            themes[f.stem] = merged
        except Exception:
            pass
    if not themes:
        themes["dark-noc"] = dict(THEME_DEFAULTS)
    return themes


# ── Dashboard config ───────────────────────────────────────────────────────────

def load_dashboard_config():
    try:
        with open(CONFIG_FILE) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ── Collector dispatch ─────────────────────────────────────────────────────────

def get_collector_map():
    from collectors import (
        proxmox, wazuh, malware_sources, docker_portainer, pbs, uptime_kuma,
        crowdsec, unifi, adguard, home_assistant, smart_health, urbackup,
        qnap, media, cloudflare, nginx_proxy, tailscale, limacharlie, custom_url,
        hyperv, adguard2, wgdashboard
    )
    return {
        "proxmox": proxmox.collect,
        "proxmox_storage": proxmox.collect_storage,
        "wazuh": wazuh.collect,
        "malware_sources": malware_sources.collect,
        "docker": docker_portainer.collect,
        "pbs": pbs.collect,
        "uptime_kuma": uptime_kuma.collect,
        "crowdsec": crowdsec.collect,
        "unifi": unifi.collect,
        "adguard": adguard.collect,
        "adguard2": adguard2.collect,
        "home_assistant": home_assistant.collect,
        "smart_health": smart_health.collect,
        "urbackup": urbackup.collect,
        "qnap": qnap.collect,
        "plex": media.collect_plex,
        "tautulli": media.collect_tautulli,
        "sonarr": media.collect_sonarr,
        "radarr": media.collect_radarr,
        "prowlarr": media.collect_prowlarr,
        "sabnzbd": media.collect_sabnzbd,
        "overseerr": media.collect_overseerr,
        "cloudflare": cloudflare.collect,
        "nginx_proxy": nginx_proxy.collect,
        "tailscale": tailscale.collect,
        "limacharlie": limacharlie.collect,
        "custom_url": custom_url.collect,
        "wan_health": unifi.collect,
        "hyperv": hyperv.collect,
        "wgdashboard": wgdashboard.collect,
    }


CARD_TYPE_META = {
    "proxmox":          {"label": "Proxmox",              "description": "Proxmox node CPU, RAM, VMs, storage",      "category": "Infrastructure", "icon": "Server"},
    "proxmox_storage":  {"label": "Proxmox Storage",      "description": "Proxmox storage pool usage donuts",         "category": "Infrastructure", "icon": "HardDrive"},
    "docker":           {"label": "Docker",               "description": "Container counts and unhealthy containers", "category": "Infrastructure", "icon": "Box"},
    "pbs":              {"label": "Proxmox Backup Server","description": "Backup tasks, last backup time, datastore", "category": "Infrastructure", "icon": "Archive"},
    "urbackup":         {"label": "URBackup",             "description": "Client backup status",                      "category": "Infrastructure", "icon": "RotateCcw"},
    "home_assistant":   {"label": "Home Assistant",       "description": "Entity counts, alerts, notifications",      "category": "Infrastructure", "icon": "Home"},
    "smart_health":     {"label": "Disk Health",          "description": "SMART disk health from Proxmox",            "category": "Infrastructure", "icon": "Activity"},
    "hyperv":           {"label": "Hyper-V",             "description": "Hyper-V VMs, CPU/memory, host resources",    "category": "Infrastructure", "icon": "Server"},
    "wazuh":            {"label": "Wazuh SIEM",           "description": "Agent status, alerts 24h",                  "category": "Security",       "icon": "Shield"},
    "malware_sources":  {"label": "Malware Detect",       "description": "Malware feed detections",                   "category": "Security",       "icon": "AlertTriangle"},
    "crowdsec":         {"label": "CrowdSec",             "description": "Bans and detections",                       "category": "Security",       "icon": "ShieldAlert"},
    "cloudflare":       {"label": "Cloudflare",           "description": "Requests, threats, WAF events",             "category": "Security",       "icon": "Cloud"},
    "limacharlie":      {"label": "LimaCharlie (LC)",    "description": "EDR detections and sensor status",            "category": "Security",       "icon": "ShieldAlert"},
    "wgdashboard":      {"label": "WGDashboard",         "description": "WireGuard VPN interfaces and peers",          "category": "Network",        "icon": "Network"},
    "unifi":            {"label": "UniFi",                "description": "WAN status, clients, IPS alerts",           "category": "Network",        "icon": "Wifi"},
    "wan_health":       {"label": "WAN Health",           "description": "WAN/internet status via UniFi",             "category": "Network",        "icon": "Wifi"},
    "tailscale":        {"label": "Tailscale",            "description": "VPN device status",                         "category": "Network",        "icon": "Network"},
    "nginx_proxy":      {"label": "Nginx Proxy Manager",  "description": "Proxy hosts and cert expiry",               "category": "Network",        "icon": "Globe"},
    "adguard":          {"label": "AdGuard · DNS1",      "description": "AdGuard Home DNS1 stats",                       "category": "Security",       "icon": "Shield"},
    "adguard2":         {"label": "AdGuard · DNS2",      "description": "AdGuard Home DNS2 stats",                       "category": "Security",       "icon": "Shield"},
    "qnap":             {"label": "NAS Storage",          "description": "QNAP NAS volumes, disks, temps",            "category": "Storage",        "icon": "Database"},
    "plex":             {"label": "Plex",                 "description": "Active streams, library counts",            "category": "Media",          "icon": "Play"},
    "tautulli":         {"label": "Tautulli",             "description": "Plex streams, plays today, top user",       "category": "Media",          "icon": "BarChart2"},
    "sonarr":           {"label": "Sonarr",               "description": "TV series, queue, missing",                 "category": "Media",          "icon": "Tv"},
    "radarr":           {"label": "Radarr",               "description": "Movies, queue, missing",                    "category": "Media",          "icon": "Film"},
    "prowlarr":         {"label": "Prowlarr",             "description": "Indexer health",                            "category": "Media",          "icon": "Search"},
    "sabnzbd":          {"label": "SABnzbd",              "description": "Download queue and speed",                  "category": "Media",          "icon": "Download"},
    "overseerr":        {"label": "Overseerr",            "description": "Media requests",                            "category": "Media",          "icon": "List"},
    "uptime_kuma":      {"label": "Uptime Kuma",          "description": "Monitor status, cert expiry",               "category": "Monitoring",     "icon": "HeartPulse"},
    "custom_url":       {"label": "Custom URL",           "description": "Fetch and display custom JSON endpoint",    "category": "Monitoring",     "icon": "ExternalLink"},
    "section_header":   {"label": "Section Header",       "description": "Visual divider / section label",            "category": "Layout",         "icon": "List"},
}

CATEGORY_ORDER = ["Infrastructure", "Security", "Network", "Storage", "Media", "Monitoring"]

# ── Trend history ──────────────────────────────────────────────────────────────

def load_trends():
    STATE_DIR.mkdir(exist_ok=True)
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_trends(trends):
    STATE_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(trends, f)


def update_trends_for(card_type, data, now_epoch, trends):
    """Append current value to trend series for cards that support graphs."""
    MAX_HOURS = 48
    cutoff = now_epoch - MAX_HOURS * 3600
    TREND_FIELDS = {
        "proxmox": ["cpu"],
        "adguard": ["block_pct", "queries"],
        "wazuh": ["alerts_24h", "high_24h"],
    }
    fields = TREND_FIELDS.get(card_type, [])
    for field in fields:
        val = data.get(field)
        if val is None:
            continue
        series_key = f"{card_type}.{field}"
        series = trends.get(series_key, [])
        series.append([now_epoch, float(val)])
        series = [[t, v] for t, v in series if t >= cutoff]
        trends[series_key] = series
    return trends


# ── Layout persistence ─────────────────────────────────────────────────────────

DEFAULT_LAYOUT = {
    "theme": "dark-noc",
    "autoTheme": False,  # permanently disabled — frontend ignores this, hardcoded dark-noc
    "cards": [],
    "sections": [],
}

# Default section definitions — mirrors NOC 1 / generate_dashboard.py structure.
# id is stable (used as card.section foreign key). label is user-editable.
DEFAULT_SECTIONS = [
    {"id": "system_status",    "label": "System Status",                  "collapsed": False},
    {"id": "security_network", "label": "Security & Network",             "collapsed": False},
    {"id": "media_downloads",  "label": "Media & Downloads",              "collapsed": False},
    {"id": "qnap_storage",     "label": "QNAP Storage Appliances",        "collapsed": False},
    {"id": "proxmox_storage",  "label": "Proxmox Storage Utilization",    "collapsed": False, "panelbox": True},
    {"id": "uptime_history",   "label": "Uptime History (last 24h)",      "collapsed": False, "panelbox": True, "historyPanel": True},
    {"id": "certs_alerts",     "label": "Certificates & Active Alerts",   "collapsed": False, "twocol": True, "certsPanel": True},
]

# Type → section id mapping used during migration of old layouts (no card.section field)
TYPE_TO_SECTION = {
    "wan_health": "system_status", "wan_health_sec": "security_network",
    "proxmox": "system_status", "home_assistant": "system_status",
    "uptime_kuma": "system_status", "docker": "system_status",
    "pbs": "system_status", "urbackup": "system_status",
    "smart_health": "system_status",
    "unifi": "security_network", "nginx_proxy": "security_network",
    "cloudflare": "security_network", "wazuh": "security_network",
    "crowdsec": "security_network", "limacharlie": "security_network",
    "adguard": "security_network", "adguard2": "security_network",
    "tailscale": "security_network", "malware_sources": "security_network",
    "wgdashboard": "security_network", "hyperv": "system_status",
    "plex": "media_downloads", "tautulli": "media_downloads",
    "sonarr": "media_downloads", "radarr": "media_downloads",
    "sabnzbd": "media_downloads", "overseerr": "media_downloads",
    "prowlarr": "media_downloads",
    "qnap": "qnap_storage",
    "proxmox_storage": "proxmox_storage",
    "uptime_kuma_detail": "uptime_history",
    "custom_url": "certs_alerts",
}



def _migrate_layout(data):
    """Add sections[] + card.section fields to old layouts. Returns (data, changed)."""
    import copy
    changed = False
    if not data.get("sections"):
        data["sections"] = copy.deepcopy(DEFAULT_SECTIONS)
        changed = True
    for card in data.get("cards", []):
        if not card.get("section"):
            card["section"] = TYPE_TO_SECTION.get(card.get("type", ""), "system_status")
            changed = True
    return data, changed


def load_layout():
    STATE_DIR.mkdir(exist_ok=True)
    if LAYOUT_FILE.exists():
        try:
            with open(LAYOUT_FILE) as f:
                data = json.load(f)
            for k, v in DEFAULT_LAYOUT.items():
                data.setdefault(k, v)
            data, changed = _migrate_layout(data)
            if changed:
                save_layout(data)
            return data
        except Exception:
            pass
    return _bootstrap_layout_from_yaml()


# Map yaml section names → section ids (for _bootstrap_layout_from_yaml)
YAML_SECTION_TO_ID = {
    "System Status": "system_status",
    "Security & Network": "security_network",
    "Media & Downloads": "media_downloads",
    "QNAP Storage Appliances": "qnap_storage",
    "Proxmox Storage Utilization": "proxmox_storage",
    "Uptime History (last 24h)": "uptime_history",
    "Certificates & Active Alerts": "certs_alerts",
}


def _bootstrap_layout_from_yaml():
    """Generate an initial layout.json from dashboard.yaml sections/cards."""
    import copy
    cfg = load_dashboard_config()
    theme_cfg = cfg.get("theme", {})
    layout = {
        "theme": "dark-noc",   # always dark-noc; auto_switch from yaml is permanently ignored
        "autoTheme": False,
        "sections": copy.deepcopy(DEFAULT_SECTIONS),
        "cards": []
    }
    import uuid
    SIZE_TO_WH = {
        "normal": (1, 2),
        "wide": (2, 2),
        "tall": (1, 4),
        "large": (2, 4),
    }
    x, y, col = 0, 0, 0
    COLS = 4
    for section in cfg.get("sections", []):
        section_id = YAML_SECTION_TO_ID.get(section.get("name", ""), "system_status")
        for card in section.get("cards", []):
            size = card.get("size", "normal")
            w, h = SIZE_TO_WH.get(size, (1, 2))
            if x + w > COLS:
                x = 0
                y += 2
            entry = {
                "id": str(uuid.uuid4()),
                "type": card.get("type", ""),
                "title": card.get("title", card.get("type", "").upper()),
                "section": section_id,
                "x": x, "y": y, "w": w, "h": h,
                "config": {
                    "graph": card.get("graph", False),
                    "graph_type": card.get("graph_type", "sparkline"),
                    "graph_field": card.get("graph_field", ""),
                    "graph_color": card.get("graph_color", ""),
                    "thresholds": card.get("thresholds", {}),
                    "refresh_seconds": cfg.get("refresh_seconds", 60),
                }
            }
            layout["cards"].append(entry)
            x += w
            if x >= COLS:
                x = 0
                y += 2
    return layout


def save_layout(layout):
    STATE_DIR.mkdir(exist_ok=True)
    with open(LAYOUT_FILE, "w") as f:
        json.dump(layout, f, indent=2)


# ── Card data cache (for ticker + status overview) ─────────────────────────────

_card_cache: dict = {}  # card_type -> {"data": {...}, "ts": float}
_sse_clients: set = set()  # set of asyncio.Queue


async def _sse_broadcast(msg: str):
    """Push a message to all connected SSE clients."""
    dead = set()
    for q in list(_sse_clients):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.add(q)
    _sse_clients.difference_update(dead)


def _push_sse_from_sync(card_type: str, data: dict):
    """Schedule SSE broadcast from a sync context (runs in uvicorn's event loop)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            msg = json.dumps({"type": "card_update", "card_type": card_type, "data": data})
            asyncio.run_coroutine_threadsafe(_sse_broadcast(msg), loop)
    except Exception:
        pass


# ── Ticker extraction ──────────────────────────────────────────────────────────

def _extract_ticker_items(cache: dict) -> tuple:
    """Extract alert/stats items from card cache. Returns (items_list, worst_level)."""
    items = []
    worst = "ok"
    level_val = {"ok": 0, "info": 0, "warn": 1, "crit": 2}

    def add(text, level):
        nonlocal worst
        items.append({"text": text, "level": level})
        if level_val.get(level, 0) > level_val.get(worst, 0):
            worst = level

    now = time.time()
    STALE = 900  # 15 min

    for card_type, entry in cache.items():
        data = entry.get("data", {})
        ts = entry.get("ts", 0)
        if now - ts > STALE:
            continue
        state = data.get("state", "ok")

        if card_type == "proxmox":
            vms_off = data.get("vms_offline", 0)
            if vms_off:
                add(f"Proxmox: {vms_off} VM(s) offline", "crit")
            cpu = data.get("cpu")
            if cpu is not None:
                if cpu > 90:
                    add(f"Proxmox CPU critical: {cpu:.0f}%", "crit")
                elif cpu > 75:
                    add(f"Proxmox CPU high: {cpu:.0f}%", "warn")

        elif card_type == "proxmox_storage":
            for pool in (data.get("pools") or []):
                pct = pool.get("pct", 0)
                name = pool.get("name", "storage")
                if pct > 90:
                    add(f"Storage {name} at {pct:.0f}%", "crit")
                elif pct > 80:
                    add(f"Storage {name} at {pct:.0f}%", "warn")

        elif card_type == "docker":
            for c in (data.get("unhealthy") or [])[:3]:
                add(f"Docker unhealthy: {c}", "crit")
            for c in (data.get("stopped") or [])[:3]:
                add(f"Docker stopped: {c}", "warn")

        elif card_type == "wazuh":
            high = data.get("high_24h", 0)
            alerts = data.get("alerts_24h", 0)
            if high > 0:
                add(f"Wazuh: {high} high-severity alert(s) in 24h", "crit")
            elif alerts > 100:
                add(f"Wazuh: {alerts} alerts in 24h", "warn")
            for a in (data.get("agents") or []):
                if a.get("status") not in ("active", "Active"):
                    add(f"Wazuh agent offline: {a.get('name', a.get('id', '?'))}", "warn")

        elif card_type == "crowdsec":
            bans = data.get("active_bans", 0) or data.get("bans", 0)
            if bans > 200:
                add(f"CrowdSec: {bans} active bans", "warn")
            d24 = data.get("decisions_24h", 0) or data.get("detections_24h", 0)
            if d24 > 1000:
                add(f"CrowdSec: {d24} detections in 24h", "warn")

        elif card_type == "uptime_kuma":
            for m in (data.get("down") or [])[:4]:
                add(f"Down: {m}", "crit")
            for m in (data.get("degraded") or [])[:2]:
                add(f"Degraded: {m}", "warn")

        elif card_type == "pbs":
            failed = data.get("failed_tasks", 0)
            if failed:
                add(f"PBS: {failed} failed backup task(s) in 24h", "crit")

        elif card_type == "urbackup":
            for c in (data.get("clients_with_issues") or [])[:3]:
                name = c if isinstance(c, str) else c.get("name", str(c))
                add(f"URBackup: {name} has issues", "warn")
            for c in (data.get("overdue") or [])[:2]:
                name = c if isinstance(c, str) else c.get("name", str(c))
                add(f"URBackup: {name} backup overdue", "warn")

        elif card_type in ("unifi", "wan_health"):
            wan_st = data.get("wan_status") or data.get("wan_state")
            if wan_st and wan_st.lower() in ("down", "error", "offline"):
                add("WAN: Internet connection DOWN", "crit")
            ips = data.get("ips_alerts_24h", 0) or data.get("ips_events", 0)
            if ips > 20:
                add(f"UniFi IPS: {ips} alerts in 24h", "warn")

        elif card_type == "cloudflare":
            threats = data.get("threats_24h", 0) or data.get("threats", 0)
            if threats > 2000:
                add(f"Cloudflare: {threats} threats blocked in 24h", "warn")

        elif card_type == "nginx_proxy":
            for c in (data.get("expired_certs") or data.get("cert_invalid") or [])[:3]:
                add(f"Cert INVALID: {c}", "crit")
            for c in (data.get("expiring_soon") or [])[:2]:
                add(f"Cert expiring soon: {c}", "warn")

        elif card_type == "smart_health":
            for d in (data.get("failed") or []):
                add(f"SMART FAIL: {d}", "crit")
            for d in (data.get("warning") or [])[:2]:
                add(f"SMART warn: {d}", "warn")

        elif card_type == "hyperv":
            stopped = data.get("stopped", 0)
            if data.get("state") == "error":
                add(f"Hyper-V: {data.get('note', 'unreachable')}", "crit")
            elif stopped > 0:
                names = [v["name"] for v in data.get("vms", []) if v.get("state") != "Running"][:3]
                add(f"Hyper-V: {stopped} VM(s) not running: {', '.join(names)}", "warn")

        elif card_type == "malware_sources":
            det = data.get("total_detections", 0) or data.get("detections", 0)
            if det > 0:
                add(f"Malware feed: {det} detection(s)", "warn")

        elif card_type == "qnap":
            for nas in (data.get("nas") or [data] if data.get("volume_pct") else []):
                pct = nas.get("volume_pct", 0)
                n = nas.get("name", "NAS")
                if pct > 90:
                    add(f"{n}: volume at {pct:.0f}%", "crit")
                elif pct > 80:
                    add(f"{n}: volume at {pct:.0f}%", "warn")

        elif card_type == "limacharlie":
            det = data.get("detections_24h", 0)
            if det > 30:
                add(f"LimaCharlie: {det} detection(s) in 24h", "warn")

        elif card_type == "home_assistant":
            alerts = data.get("alerts", 0) or data.get("persistent_notifications", 0)
            if alerts > 5:
                add(f"Home Assistant: {alerts} active alert(s)", "warn")

        elif state in ("crit", "critical", "error"):
            label = CARD_TYPE_META.get(card_type, {}).get("label", card_type)
            add(f"{label}: {state.upper()}", "crit")
        elif state == "warn":
            label = CARD_TYPE_META.get(card_type, {}).get("label", card_type)
            add(f"{label}: WARNING", "warn")

    # Positive stats when all clear
    if not items:
        total = len(cache)
        if total > 0:
            add(f"All {total} monitored service(s) nominal", "ok")
        prox = cache.get("proxmox", {}).get("data", {})
        if prox.get("cpu") is not None:
            add(f"Proxmox: CPU {prox['cpu']:.0f}% · RAM {prox.get('mem_pct', 0):.0f}%", "ok")
        ag = cache.get("adguard", {}).get("data", {})
        if ag.get("block_pct") is not None and ag.get("block_pct", 0) > 0:
            add(f"AdGuard: blocking {float(ag['block_pct']):.1f}% of queries", "ok")
        uk = cache.get("uptime_kuma", {}).get("data", {})
        if uk.get("up_count"):
            add(f"Uptime Kuma: {uk['up_count']} monitors UP", "ok")
        if not items:
            add("NOC Dashboard — MRDTech // ANTON — All Systems Nominal", "ok")

    return items, worst



# ── NOC Intelligence / Health Score persistence ───────────────────────────────

_HEALTH_SNAPSHOT_MIN_INTERVAL = 25
_last_health_snapshot_ts = 0
_last_incident_state: dict[str, str] = {}


def _db():
    STATE_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_score_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            pct REAL NOT NULL,
            breakdown_json TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_score_snapshots_ts ON health_score_snapshots(ts)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_state_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            source TEXT NOT NULL,
            item TEXT NOT NULL,
            old_state TEXT,
            new_state TEXT NOT NULL,
            detail TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_state_changes_ts ON health_state_changes(ts)")
    return conn


def _state_ok(state):
    return str(state or "").lower() in ("ok", "up", "running", "active", "online", "healthy", "success")


def _pct(good, total):
    try:
        good = int(good or 0); total = int(total or 0)
    except Exception:
        return 0
    return 100 if total <= 0 else round(max(0, min(100, 100 * good / total)))


def _cat(source, label, good, total, detail=None):
    return {"source": source, "label": label, "good": int(good or 0), "total": int(total or 0), "pct": _pct(good, total), "detail": detail or []}


def _current_data(card_type):
    return (_card_cache.get(card_type) or {}).get("data") or {}


def _health_breakdown_from_cache():
    cats = []
    prox = _current_data("proxmox")
    if prox:
        total = int(prox.get("vms_total") or 0)
        good = int(prox.get("vms_running") or 0)
        cats.append(_cat("proxmox", "Proxmox VMs", good, total, prox.get("down_vms") or []))

    dock = _current_data("docker")
    if dock:
        total = int(dock.get("total") or 0)
        bad = len(dock.get("bad") or dock.get("bad_containers") or dock.get("unhealthy") or [])
        good = max(0, total - bad)
        cats.append(_cat("docker", "Docker Containers", good, total, dock.get("bad") or []))

    kuma = _current_data("uptime_kuma")
    if kuma:
        total = int(kuma.get("total") or 0)
        good = int(kuma.get("up") or kuma.get("up_count") or 0)
        detail = list(kuma.get("down") or []) + [str(x) for x in (kuma.get("other") or [])]
        cats.append(_cat("uptime_kuma", "Uptime Kuma", good, total, detail))

    pbs = _current_data("pbs")
    if pbs:
        ok = int(pbs.get("ok") or 0); fail = int(pbs.get("fail") or pbs.get("failed_tasks") or 0); run = int(pbs.get("run") or 0)
        total = ok + fail + run
        cats.append(_cat("pbs", "PBS Tasks", ok + run, total, [] if not fail else [f"{fail} failed task(s)"]))

    urb = _current_data("urbackup")
    if urb:
        clients = urb.get("clients") or []
        total = int(urb.get("total") or len(clients) or 0)
        good = sum(1 for c in clients if (c.get("state") or "ok") == "ok") if clients else int(urb.get("online") or 0)
        cats.append(_cat("urbackup", "UrBackup Clients", good, total, urb.get("problems") or []))

    waz = _current_data("wazuh")
    if waz:
        total = int(waz.get("total") or 0)
        good = int(waz.get("active") or 0)
        cats.append(_cat("wazuh", "Wazuh Agents", good, total, waz.get("down") or []))

    total_checks = sum(c["total"] for c in cats)
    good_checks = sum(c["good"] for c in cats)
    pct = _pct(good_checks, total_checks)
    state = "ok" if pct >= 95 else "warn" if pct >= 90 else "crit"
    return {"pct": pct, "state": state, "good": good_checks, "total": total_checks, "categories": cats, "ts": int(time.time())}


def _incident_items_for_health(health):
    items = []
    for c in health.get("categories", []):
        state = "ok" if c["good"] >= c["total"] else "crit" if c["pct"] < 90 else "warn"
        items.append((c["source"], "__category__", state, f"{c['label']}: {c['good']}/{c['total']}"))
        for detail in c.get("detail") or []:
            items.append((c["source"], str(detail), "crit" if state == "crit" else "warn", str(detail)))
    return items


def _maybe_record_health_snapshot(force=False):
    global _last_health_snapshot_ts, _last_incident_state
    now = int(time.time())
    health = _health_breakdown_from_cache()
    if health.get("total", 0) <= 0:
        return health
    with _db() as conn:
        if force or now - _last_health_snapshot_ts >= _HEALTH_SNAPSHOT_MIN_INTERVAL:
            conn.execute(
                "INSERT INTO health_score_snapshots(ts, pct, breakdown_json) VALUES (?, ?, ?)",
                (now, float(health["pct"]), json.dumps(health["categories"])),
            )
            conn.execute("DELETE FROM health_score_snapshots WHERE ts < ?", (now - 31 * 86400,))
            _last_health_snapshot_ts = now
        for source, item, state, detail in _incident_items_for_health(health):
            key = f"{source}:{item}"
            old = _last_incident_state.get(key)
            if old is None:
                _last_incident_state[key] = state
            elif old != state:
                conn.execute(
                    "INSERT INTO health_state_changes(ts, source, item, old_state, new_state, detail) VALUES (?, ?, ?, ?, ?, ?)",
                    (now, source, item, old, state, detail),
                )
                _last_incident_state[key] = state
    return health


def _health_history(range_name="24h"):
    seconds = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}.get(range_name, 86400)
    since = int(time.time()) - seconds
    with _db() as conn:
        rows = conn.execute(
            "SELECT ts, pct FROM health_score_snapshots WHERE ts >= ? ORDER BY ts ASC",
            (since,),
        ).fetchall()
    return [{"ts": int(r["ts"]), "pct": round(float(r["pct"]), 1)} for r in rows]


def _health_incidents(limit=20):
    with _db() as conn:
        rows = conn.execute(
            "SELECT ts, source, item, old_state, new_state, detail FROM health_state_changes ORDER BY ts DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def _backup_coverage_from_cache():
    data = _current_data("urbackup")
    clients = data.get("clients") or []
    now = time.time()
    file_good = image_good = 0
    out_clients = []
    for c in clients:
        file_recent = bool(c.get("file_recent", (c.get("state") or "ok") == "ok"))
        image_days = c.get("image_days")
        image_recent = bool(c.get("image_recent", image_days is not None and image_days <= 8))
        file_good += 1 if file_recent else 0
        image_good += 1 if image_recent else 0
        status = "ok" if file_recent and image_recent else "warn" if file_recent or image_recent else "crit"
        out_clients.append({
            "name": c.get("name", "?"), "last_file_backup": c.get("last_file_backup") or c.get("ago") or "?",
            "days_since_image_backup": image_days, "status": status,
        })
    total = len(clients) or int(data.get("total") or 0)
    return {"file_pct": _pct(file_good, total), "image_pct": _pct(image_good, total), "file_good": file_good, "image_good": image_good, "total": total, "clients": out_clients}


def _security_posture_from_cache():
    waz = _current_data("wazuh"); cs = _current_data("crowdsec"); lc = _current_data("limacharlie")
    waz_high = int(waz.get("high_24h") or waz.get("high_alerts") or 0)
    bans = int(cs.get("bans") or cs.get("active_bans") or 0)
    lc_det = int(lc.get("detections_24h") or 0)
    score = max(0, 100 - (waz_high * 25) - min(25, bans // 25) - min(25, lc_det * 5))
    state = "crit" if waz_high > 0 else "ok" if score >= 95 else "warn" if score >= 90 else "crit"
    return {"pct": score, "state": state, "breakdown": {"wazuh_high_crit_24h": waz_high, "crowdsec_active_bans": bans, "limacharlie_detections_24h": lc_det}}


def _storage_health_from_cache():
    volumes = []
    qnap = _current_data("qnap")
    for unit in qnap.get("units") or []:
        label = unit.get("label") or unit.get("host") or "QNAP"
        for v in unit.get("volumes") or []:
            pct = float(v.get("pct") or 0)
            volumes.append({"name": f"{label} {v.get('name','volume')}", "pct": pct, "used": v.get("used_t"), "total": v.get("total_t"), "source": "qnap"})
    pbs = _current_data("pbs")
    for ds in pbs.get("datastores") or []:
        volumes.append({"name": f"PBS {ds.get('name','datastore')}", "pct": float(ds.get("pct") or 0), "source": "pbs"})
    total_pct = round(sum(v["pct"] for v in volumes) / len(volumes), 1) if volumes else 0
    return {"aggregate_pct": total_pct, "volumes": volumes}


def _cert_expiry_from_cache():
    certs = []
    npm = _current_data("nginx_proxy")
    for c in npm.get("cert_list") or []:
        certs.append({"name": c.get("name", "?"), "days": c.get("days"), "valid": c.get("valid", True), "source": "npm"})
    # Keep Kuma cert validity as supplemental visibility; it catches externally invalid certs.
    for c in (_current_data("uptime_kuma").get("certs") or []):
        name = c.get("name", "?")
        if not any(x["name"] == name for x in certs):
            certs.append({"name": name, "days": c.get("days"), "valid": c.get("valid", True), "source": "uptime_kuma"})
    certs.sort(key=lambda c: (c.get("valid", True), 9999 if c.get("days") is None else c.get("days")))
    flagged = [c for c in certs if ("portainer" in c.get("name", "").lower()) and (not c.get("valid", True) or (c.get("days") is not None and c.get("days") < 0))]
    return {"certs": certs, "flagged": flagged}


def _intelligence_payload():
    health = _maybe_record_health_snapshot()
    return {
        "health": health,
        "history": {"24h": _health_history("24h"), "7d": _health_history("7d"), "30d": _health_history("30d")},
        "incidents": _health_incidents(20),
        "backup": _backup_coverage_from_cache(),
        "security": _security_posture_from_cache(),
        "storage": _storage_health_from_cache(),
        "certificates": _cert_expiry_from_cache(),
        "ts": int(time.time()),
    }

# ── FastAPI app ────────────────────────────────────────────────────────────────

app = FastAPI(title="NOC Dashboard API", docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_collector_map = None


def get_collectors():
    global _collector_map
    if _collector_map is None:
        try:
            _collector_map = get_collector_map()
        except Exception as e:
            print(f"WARNING: collector import error: {e}", file=sys.stderr)
            _collector_map = {}
    return _collector_map



PUBLIC_API_PATHS = {
    "/api/auth/status",
    "/api/auth/setup",
    "/api/auth/login",
}


@app.middleware("http")
async def require_auth_for_api(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        cfg_json = load_config_json()
        if not _verify_session_token(cfg_json, request.cookies.get(SESSION_COOKIE)):
            return JSONResponse({"detail": "authentication required"}, status_code=401)
    return await call_next(request)


@app.get("/api/auth/status")
def api_auth_status(request: Request):
    cfg_json = load_config_json()
    admin = _get_admin(cfg_json)
    authenticated = _verify_session_token(cfg_json, request.cookies.get(SESSION_COOKIE))
    return {
        "authenticated": authenticated,
        "needs_setup": admin is None,
        "username": admin.get("username") if admin and authenticated else None,
        "role": admin.get("role", "Administrator") if admin and authenticated else None,
    }


@app.post("/api/auth/setup")
async def api_auth_setup(request: Request):
    cfg_json = load_config_json()
    if _get_admin(cfg_json):
        raise HTTPException(status_code=409, detail="admin user already exists")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    confirm = str(body.get("confirm_password", ""))
    remember = body.get("remember", True) is not False
    if not username:
        raise HTTPException(status_code=400, detail="username is required")
    if not _password_ok(password):
        raise HTTPException(status_code=400, detail="password must be at least 8 characters")
    if not hmac.compare_digest(password, confirm):
        raise HTTPException(status_code=400, detail="passwords do not match")
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cfg_json["admin"] = {"username": username, "password_hash": password_hash}
    cfg_json["sessions"] = {}
    token = _create_session(cfg_json)
    return _auth_response({"ok": True, "username": username}, token, remember)


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    cfg_json = load_config_json()
    admin = _get_admin(cfg_json)
    if not admin:
        raise HTTPException(status_code=409, detail="admin setup required")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    remember = body.get("remember", True) is not False
    valid_user = hmac.compare_digest(username, str(admin.get("username", "")))
    valid_pass = bcrypt.checkpw(password.encode("utf-8"), str(admin.get("password_hash", "")).encode("utf-8"))
    if not (valid_user and valid_pass):
        raise HTTPException(status_code=401, detail="invalid username or password")
    token = _create_session(cfg_json)
    return _auth_response({"ok": True, "username": admin.get("username")}, token, remember)


@app.post("/api/auth/logout")
def api_auth_logout(request: Request):
    cfg_json = load_config_json()
    _clear_session_token(cfg_json, request.cookies.get(SESSION_COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.post("/api/auth/change-password")
async def api_auth_change_password(request: Request):
    cfg_json = load_config_json()
    admin = _get_admin(cfg_json)
    if not admin:
        raise HTTPException(status_code=409, detail="admin setup required")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    current = str(body.get("current_password", ""))
    new_password = str(body.get("new_password", ""))
    confirm = str(body.get("confirm_password", ""))
    if not bcrypt.checkpw(current.encode("utf-8"), str(admin.get("password_hash", "")).encode("utf-8")):
        raise HTTPException(status_code=401, detail="current password is incorrect")
    if not _password_ok(new_password):
        raise HTTPException(status_code=400, detail="new password must be at least 8 characters")
    if not hmac.compare_digest(new_password, confirm):
        raise HTTPException(status_code=400, detail="new passwords do not match")
    admin["password_hash"] = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    # Changing passwords invalidates every other session. Basic hygiene. Apparently necessary.
    current_hash = _hash_token(request.cookies.get(SESSION_COOKIE, ""))
    current_session = cfg_json.get("sessions", {}).get(current_hash)
    cfg_json["sessions"] = {current_hash: current_session} if current_session else {}
    save_config_json(cfg_json)
    return {"ok": True}

# ── API routes ─────────────────────────────────────────────────────────────────

@app.get("/api/card-types")
def api_card_types():
    return {k: v for k, v in CARD_TYPE_META.items()}


@app.get("/api/themes")
def api_themes():
    return load_all_themes()


@app.get("/api/layout")
def api_get_layout():
    return load_layout()


@app.post("/api/layout")
async def api_save_layout(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")
    save_layout(body)
    return {"ok": True}


@app.get("/api/config")
def api_config():
    cfg = load_dashboard_config()
    top_bar = cfg.get("top_bar", {})
    return {
        "title": top_bar.get("title", "NOC Dashboard"),
        "subtitle": top_bar.get("subtitle", ""),
        "show_updated": top_bar.get("show_updated", True),
        "show_overall_status": top_bar.get("show_overall_status", True),
        "overall_status_logic": top_bar.get("overall_status_logic", "worst"),
    }


@app.get("/api/data/{card_type}")
def api_data(card_type: str, request: Request):
    """Run collector and return live data."""
    collectors = get_collectors()
    fn = collectors.get(card_type)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"no collector for '{card_type}'")

    card_cfg = {"type": card_type}
    qp = dict(request.query_params)
    if "thresholds" in qp:
        try:
            card_cfg["thresholds"] = json.loads(qp["thresholds"])
        except Exception:
            pass
    for k in ("graph_field", "graph_type", "graph_color"):
        if k in qp:
            card_cfg[k] = qp[k]

    now = time.time()
    try:
        t0 = time.time()
        data = fn(E, card_cfg)
        elapsed = round(time.time() - t0, 3)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[{card_type}] ERROR: {e}\n{tb}", file=sys.stderr)
        data = {"state": "error", "note": str(e)[:200]}
        elapsed = 0

    # Cache for ticker + status overview
    _card_cache[card_type] = {"data": data, "ts": now}

    # Update trends
    try:
        trends = load_trends()
        if data.get("state") not in ("error",):
            trends = update_trends_for(card_type, data, int(now), trends)
            save_trends(trends)
    except Exception:
        pass

    # Include trend data in response
    try:
        trend_data = {}
        trends = load_trends()
        for k, v in trends.items():
            if k.startswith(card_type + "."):
                trend_data[k.split(".", 1)[1]] = [val for _, val in v[-60:]]
        if trend_data:
            data["_trends"] = trend_data
    except Exception:
        pass

    data["_elapsed"] = elapsed
    data["_ts"] = int(now)

    # Push to SSE clients (non-blocking)
    _push_sse_from_sync(card_type, data)

    # Record alert events to persistent history
    try:
        _record_alert_events(card_type, data)
    except Exception:
        pass

    # Health Score snapshots/incidents live in SQLite. Record at most once per poll cycle.
    try:
        _maybe_record_health_snapshot()
    except Exception:
        pass

    return data


@app.get("/api/data/uptime_kuma_detail")
def api_uptime_kuma_detail():
    """
    Uptime Kuma history hbar data.
    Builds 24-cell arrays from the kuma trend data stored in trends.json.
    Falls back to current status_map if no trend history yet.
    """
    import time as _time
    now = int(_time.time())
    hours = 24

    # Try to get trend data from trends.json
    try:
        trends = load_trends()
    except Exception:
        trends = {}

    monitors_out = []

    # Check if we have kuma history trends
    kuma_trends = {k.split(".", 1)[1]: v for k, v in trends.items()
                   if k.startswith("uptime_kuma.")}

    if kuma_trends:
        start = now - hours * 3600
        for name, series in sorted(kuma_trends.items()):
            buckets: list = [None] * hours
            for ts, val in series:
                idx = int((ts - start) // 3600)
                if 0 <= idx < hours:
                    # val: 1=up, 0=down, 0.5=other — map to our codes
                    sev = 3 if val == 0 else 2 if (0 < val < 1) else 1
                    cur_sev = {None: 0, 1: 1, 2: 2, 0: 3}.get(buckets[idx], 0)
                    if sev >= cur_sev:
                        buckets[idx] = 0 if sev == 3 else (2 if sev == 2 else 1)
            cells = [b if b is not None else -1 for b in buckets]
            monitors_out.append({"name": name, "cells": cells})
    else:
        # Fall back to current status_map from cache
        uk_cache = _card_cache.get("uptime_kuma", {}).get("data", {})
        status_map = uk_cache.get("status_map", {})
        for name, val in sorted(status_map.items()):
            # Show only current status in last cell
            cells = [-1] * (hours - 1) + [val]
            monitors_out.append({"name": name, "cells": cells})

    return {
        "state": "ok",
        "history_monitors": monitors_out,
        "_ts": now,
    }


@app.get("/api/ticker")
def api_ticker():
    """Aggregated alerts and stats for the scrolling ticker bar."""
    items, worst = _extract_ticker_items(_card_cache)
    return {"items": items, "worst": worst, "ts": int(time.time())}


@app.get("/api/status-overview")
def api_status_overview():
    """Counts of ok/warn/crit across all recently-seen cards."""
    now = time.time()
    STALE = 900
    counts = {"ok": 0, "warn": 0, "crit": 0, "error": 0, "unknown": 0}
    for card_type, entry in _card_cache.items():
        if now - entry.get("ts", 0) > STALE:
            continue
        state = entry.get("data", {}).get("state", "unknown")
        if state in ("crit", "critical"):
            counts["crit"] += 1
        elif state == "warn":
            counts["warn"] += 1
        elif state == "ok":
            counts["ok"] += 1
        elif state == "error":
            counts["error"] += 1
        else:
            counts["unknown"] += 1
    worst = "ok"
    if counts["crit"] + counts["error"] > 0:
        worst = "crit"
    elif counts["warn"] > 0:
        worst = "warn"
    return {**counts, "worst": worst, "total": sum(counts.values()), "ts": int(time.time())}


@app.get("/api/intelligence")
def api_intelligence():
    """NOC Intelligence sidebar payload: health score, trends, incidents, backups, security, storage, and certs."""
    return _intelligence_payload()


@app.get("/api/events")
async def api_sse():
    """Server-Sent Events stream for live card data updates."""
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _sse_clients.add(q)

    async def stream():
        try:
            yield f"data: {json.dumps({'type': 'connected', 'ts': int(time.time())})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat', 'ts': int(time.time())})}\n\n"
        except Exception:
            pass
        finally:
            _sse_clients.discard(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.get("/api/health")
def api_health():
    return {"ok": True, "ts": int(time.time())}



# ── Alert history persistence ──────────────────────────────────────────────────

ALERT_HISTORY_FILE = STATE_DIR / "alert_history.json"
MAX_ALERT_HISTORY = 500  # keep last 500 events


def load_alert_history() -> list:
    STATE_DIR.mkdir(exist_ok=True)
    if ALERT_HISTORY_FILE.exists():
        try:
            with open(ALERT_HISTORY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_alert_history(events: list):
    STATE_DIR.mkdir(exist_ok=True)
    with open(ALERT_HISTORY_FILE, "w") as f:
        json.dump(events, f)


def _extract_alert_events(card_type: str, data: dict) -> list:
    """Extract named alert events from a card data payload.
    Returns list of {text, level} dicts.
    """
    events = []
    label = CARD_TYPE_META.get(card_type, {}).get("label", card_type)
    state = data.get("state", "ok")

    if card_type == "proxmox":
        vms_off = data.get("vms_offline", 0)
        if vms_off:
            events.append({"text": f"{label}: {vms_off} VM(s) offline", "level": "crit"})
        for vm in (data.get("down_vms") or []):
            events.append({"text": f"{label}: VM offline — {vm}", "level": "crit"})
        cpu = data.get("cpu_pct") or data.get("cpu")
        if cpu is not None:
            if cpu > 90:
                events.append({"text": f"{label}: CPU critical {cpu:.0f}%", "level": "crit"})
            elif cpu > 75:
                events.append({"text": f"{label}: CPU high {cpu:.0f}%", "level": "warn"})

    elif card_type == "proxmox_storage":
        for pool in (data.get("pools") or []):
            pct = pool.get("pct", 0)
            name = pool.get("name", "storage")
            if pct > 90:
                events.append({"text": f"{label}: {name} at {pct:.0f}%", "level": "crit"})
            elif pct > 80:
                events.append({"text": f"{label}: {name} at {pct:.0f}%", "level": "warn"})
        for sname, sdata in (data.get("storage") or {}).items():
            pct = sdata.get("used_pct") or sdata.get("pct") or 0
            if pct > 90:
                events.append({"text": f"{label}: {sname} at {pct:.0f}%", "level": "crit"})
            elif pct > 80:
                events.append({"text": f"{label}: {sname} at {pct:.0f}%", "level": "warn"})

    elif card_type == "docker":
        for c in (data.get("bad_containers") or data.get("unhealthy") or [])[:10]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            st = (f" ({c.get('state', c.get('status', '?'))})" if isinstance(c, dict) else "")
            events.append({"text": f"Docker: {name}{st} unhealthy", "level": "crit"})
        for c in (data.get("stopped") or [])[:5]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            events.append({"text": f"Docker: {name} stopped", "level": "warn"})

    elif card_type == "wazuh":
        high = data.get("high_alerts") or data.get("high_24h", 0)
        alerts = data.get("alerts_24h", 0)
        if high > 0:
            events.append({"text": f"Wazuh: {high} high-severity alert(s) in 24h", "level": "crit"})
        elif alerts > 100:
            events.append({"text": f"Wazuh: {alerts} total alerts in 24h", "level": "warn"})
        for a in (data.get("down_agents") or data.get("agents") or []):
            if isinstance(a, dict):
                status = a.get("status", "")
                if status and status.lower() not in ("active",):
                    name = a.get("name", a.get("id", str(a)))
                    events.append({"text": f"Wazuh: agent offline — {name}", "level": "warn"})

    elif card_type == "crowdsec":
        bans = data.get("active_bans", 0) or data.get("bans", 0)
        if bans > 200:
            events.append({"text": f"CrowdSec: {bans} active bans", "level": "warn"})
        d24 = data.get("decisions_24h", 0) or data.get("detections_24h", 0)
        if d24 > 1000:
            events.append({"text": f"CrowdSec: {d24} detections in 24h", "level": "warn"})

    elif card_type == "uptime_kuma":
        for m in (data.get("down") or [])[:10]:
            name = m if isinstance(m, str) else m.get("name", str(m))
            events.append({"text": f"Down: {name}", "level": "crit"})
        for m in (data.get("degraded") or [])[:5]:
            name = m if isinstance(m, str) else m.get("name", str(m))
            events.append({"text": f"Degraded: {name}", "level": "warn"})

    elif card_type == "pbs":
        failed = data.get("failed_tasks", 0)
        if failed:
            events.append({"text": f"PBS: {failed} failed backup task(s) in 24h", "level": "crit"})

    elif card_type == "urbackup":
        for c in (data.get("clients_with_issues") or [])[:5]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            events.append({"text": f"URBackup: {name} has issues", "level": "warn"})
        for c in (data.get("overdue") or [])[:3]:
            name = c if isinstance(c, str) else c.get("name", str(c))
            events.append({"text": f"URBackup: {name} backup overdue", "level": "warn"})

    elif card_type in ("unifi", "wan_health"):
        wan_st = data.get("wan_status") or data.get("wan_state", "")
        if wan_st and wan_st.lower() in ("down", "error", "offline"):
            events.append({"text": "WAN: Internet connection DOWN", "level": "crit"})
        ips = data.get("ips_alerts_24h", 0) or data.get("ips_events", 0)
        if ips > 20:
            events.append({"text": f"UniFi IPS: {ips} alerts in 24h", "level": "warn"})

    elif card_type == "cloudflare":
        threats = data.get("threats_24h", 0) or data.get("threats", 0)
        if threats > 2000:
            events.append({"text": f"Cloudflare: {threats} threats blocked in 24h", "level": "warn"})

    elif card_type == "nginx_proxy":
        for c in (data.get("expired_certs") or data.get("cert_invalid") or [])[:5]:
            events.append({"text": f"Cert INVALID: {c}", "level": "crit"})
        for c in (data.get("expiring_soon") or [])[:3]:
            events.append({"text": f"Cert expiring soon: {c}", "level": "warn"})

    elif card_type == "smart_health":
        for d in (data.get("failed") or []):
            events.append({"text": f"SMART FAIL: {d}", "level": "crit"})
        for d in (data.get("warning") or [])[:3]:
            events.append({"text": f"SMART warning: {d}", "level": "warn"})

    elif card_type == "hyperv":
        stopped = data.get("stopped", 0)
        if data.get("state") == "error":
            events.append({"text": f"Hyper-V: {data.get('note', 'unreachable')}", "level": "crit"})
        elif stopped > 0:
            names = [v["name"] for v in data.get("vms", []) if v.get("state") != "Running"][:3]
            events.append({"text": f"Hyper-V: {stopped} VM(s) not running: {', '.join(names)}", "level": "warn"})

    elif card_type == "malware_sources":
        det = data.get("total_detections", 0) or data.get("detections", 0)
        if det > 0:
            events.append({"text": f"Malware feed: {det} detection(s)", "level": "warn"})

    elif card_type == "qnap":
        for nas in (data.get("nas") or ([data] if data.get("volume_pct") else [])):
            pct = nas.get("volume_pct", 0)
            n = nas.get("name", "NAS")
            if pct > 90:
                events.append({"text": f"{n}: volume at {pct:.0f}%", "level": "crit"})
            elif pct > 80:
                events.append({"text": f"{n}: volume at {pct:.0f}%", "level": "warn"})
            for disk in (nas.get("disks") or []):
                st = disk.get("health") or disk.get("status", "")
                if st and st.lower() not in ("good", "ok", "normal"):
                    events.append({"text": f"{n}: disk {disk.get('id','?')} — {st}", "level": "warn"})

    elif card_type == "limacharlie":
        det = data.get("detections_24h", 0)
        if det > 30:
            events.append({"text": f"LimaCharlie: {det} detection(s) in 24h", "level": "warn"})
        for s in (data.get("offline_sensors") or [])[:3]:
            events.append({"text": f"LimaCharlie: sensor offline — {s}", "level": "warn"})

    elif card_type == "home_assistant":
        for n in (data.get("notifications") or [])[:5]:
            text = n if isinstance(n, str) else n.get("message", n.get("title", str(n)))
            events.append({"text": f"HA: {text}", "level": "warn"})
        for e in (data.get("entity_unavailable") or [])[:3]:
            events.append({"text": f"HA: entity unavailable — {e}", "level": "warn"})

    elif card_type == "tailscale":
        for d in (data.get("offline_devices") or [])[:5]:
            name = d if isinstance(d, str) else d.get("name", d.get("hostname", str(d)))
            events.append({"text": f"Tailscale: {name} offline", "level": "warn"})

    # Fallback for unhandled card types in error/crit state
    if not events and state in ("crit", "critical", "error"):
        note = data.get("note", "")
        events.append({"text": f"{label}: {state.upper()}{' — ' + note if note else ''}", "level": "crit"})
    elif not events and state == "warn":
        events.append({"text": f"{label}: WARNING", "level": "warn"})

    return events


@app.get("/api/alert-history")
def api_get_alert_history():
    """Return persisted alert event history."""
    return {"events": load_alert_history(), "ts": int(time.time())}


@app.post("/api/alert-history/clear")
async def api_clear_alert_history():
    """Clear the alert history file."""
    save_alert_history([])
    return {"ok": True}


def _record_alert_events(card_type: str, data: dict):
    """Extract and append new alert events to persistent history.
    Deduplicates within the same minute to prevent log spam on fast refresh.
    """
    events = _extract_alert_events(card_type, data)
    if not events:
        return
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    history = load_alert_history()
    existing_texts_this_minute = {
        e["text"] for e in history
        if e.get("ts", "")[:16] == now_iso[:16]
    }
    new_entries = []
    for ev in events:
        if ev["text"] not in existing_texts_this_minute:
            new_entries.append({
                "text": ev["text"],
                "level": ev["level"],
                "card_type": card_type,
                "ts": now_iso,
            })
            existing_texts_this_minute.add(ev["text"])

    if not new_entries:
        return
    merged = new_entries + history
    merged = merged[:MAX_ALERT_HISTORY]
    save_alert_history(merged)

    # Broadcast new events to all open SSE clients
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            msg = json.dumps({"type": "alert_history_update", "new_events": new_entries})
            asyncio.run_coroutine_threadsafe(_sse_broadcast(msg), loop)
    except Exception:
        pass


# ── Integration config management ─────────────────────────────────────────────
# state/config.json stores all integration credentials.
# Structure: {"integrations": {"proxmox": {"url": ..., "token_id": ..., ...}, ...}}
# .env is the fallback; config.json values win.

# Maps integration type -> env var names for each field
# Fields are in order: url, then auth fields
INTEGRATION_FIELDS = {
    "proxmox": [
        {"key": "PROXMOX_HOST", "label": "Host URL", "placeholder": "https://10.10.10.251:8006", "type": "text"},
        {"key": "PROXMOX_TOKEN_ID", "label": "Token ID", "placeholder": "root@pam!hermes", "type": "text"},
        {"key": "PROXMOX_TOKEN_SECRET", "label": "Token Secret", "placeholder": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx", "type": "password"},
    ],
    "pbs": [
        {"key": "PBS_URL", "label": "URL", "placeholder": "https://10.10.10.77:8007", "type": "text"},
        {"key": "PBS_USERNAME", "label": "Username", "placeholder": "root@pam", "type": "text"},
        {"key": "PBS_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "docker": [
        {"key": "PORTAINER_URL", "label": "Portainer URL", "placeholder": "https://10.10.10.237:9005", "type": "text"},
        {"key": "PORTAINER_USERNAME", "label": "Username", "placeholder": "admin", "type": "text"},
        {"key": "PORTAINER_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "urbackup": [
        {"key": "URBACKUP_URL", "label": "URL", "placeholder": "http://10.10.10.76:55414", "type": "text"},
        {"key": "URBACKUP_USERNAME", "label": "Username", "placeholder": "michaeld", "type": "text"},
        {"key": "URBACKUP_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "home_assistant": [
        {"key": "HASS_URL", "label": "URL", "placeholder": "http://10.10.10.105:8123", "type": "text"},
        {"key": "HASS_TOKEN", "label": "Long-Lived Access Token", "placeholder": "", "type": "password"},
    ],
    "wazuh": [
        {"key": "WAZUH_API_URL", "label": "API URL", "placeholder": "https://10.10.10.233:55000", "type": "text"},
        {"key": "WAZUH_API_USER", "label": "Username", "placeholder": "hermes", "type": "text"},
        {"key": "WAZUH_API_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "crowdsec": [
        {"key": "CROWDSEC_API_URL", "label": "API URL", "placeholder": "http://10.10.10.237:18080", "type": "text"},
        {"key": "CROWDSEC_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
        {"key": "CROWDSEC_MACHINE_USER", "label": "Machine User (optional)", "placeholder": "hermes-reader", "type": "text"},
        {"key": "CROWDSEC_MACHINE_PASS", "label": "Machine Pass (optional)", "placeholder": "", "type": "password"},
    ],
    "cloudflare": [
        {"key": "CLOUDFLARE_TOKEN", "label": "API Token", "placeholder": "", "type": "password"},
        {"key": "CLOUDFLARE_ZONE_ID", "label": "Zone ID", "placeholder": "", "type": "text"},
    ],
    "limacharlie": [
        {"key": "LIMACHARLIE_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
        {"key": "LIMACHARLIE_OID", "label": "Organization ID (OID)", "placeholder": "", "type": "text"},
    ],
    "unifi": [
        {"key": "UNIFI_URL", "label": "URL", "placeholder": "https://10.10.10.1", "type": "text"},
        {"key": "UNIFI_USERNAME", "label": "Username", "placeholder": "admin", "type": "text"},
        {"key": "UNIFI_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "tailscale": [
        {"key": "TAILSCALE_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "nginx_proxy": [
        {"key": "NPM_URL", "label": "URL", "placeholder": "http://10.10.10.237:81", "type": "text"},
        {"key": "NPM_EMAIL", "label": "Email", "placeholder": "admin@example.com", "type": "text"},
        {"key": "NPM_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "adguard": [
        {"key": "ADGUARD_URL", "label": "URL", "placeholder": "http://10.10.10.21", "type": "text"},
        {"key": "ADGUARD_USERNAME", "label": "Username", "placeholder": "mdziegiel", "type": "text"},
        {"key": "ADGUARD_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "adguard2": [
        {"key": "ADGUARD2_URL", "label": "URL", "placeholder": "http://10.10.10.x:3000", "type": "text"},
        {"key": "ADGUARD2_USERNAME", "label": "Username", "placeholder": "admin", "type": "text"},
        {"key": "ADGUARD2_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "wgdashboard": [
        {"key": "WG_URL", "label": "URL", "placeholder": "http://10.10.10.x:10086", "type": "text"},
        {"key": "WG_USERNAME", "label": "Username", "placeholder": "admin", "type": "text"},
        {"key": "WG_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "uptime_kuma": [
        {"key": "UPTIME_KUMA_URL", "label": "URL", "placeholder": "http://10.10.10.237:3661", "type": "text"},
        {"key": "UPTIME_KUMA_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "qnap": [
        {"key": "QNAP1_HOST", "label": "QNAP1 Host", "placeholder": "http://10.10.10.x:8080", "type": "text"},
        {"key": "QNAP2_HOST", "label": "QNAP2 Host (optional)", "placeholder": "http://10.10.10.x:8080", "type": "text"},
        {"key": "QNAP3_HOST", "label": "QNAP3 Host (optional)", "placeholder": "http://10.10.10.x:8080", "type": "text"},
        {"key": "QNAP_USERNAME", "label": "Username", "placeholder": "admin", "type": "text"},
        {"key": "QNAP_PASSWORD", "label": "Password", "placeholder": "", "type": "password"},
    ],
    "plex": [
        {"key": "PLEX_URL", "label": "URL", "placeholder": "http://10.10.10.101:32400", "type": "text"},
        {"key": "PLEX_TOKEN", "label": "X-Plex-Token", "placeholder": "", "type": "password"},
    ],
    "tautulli": [
        {"key": "TAUTULLI_URL", "label": "URL", "placeholder": "http://10.10.10.101:8181", "type": "text"},
        {"key": "TAUTULLI_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "sonarr": [
        {"key": "SONARR_URL", "label": "URL", "placeholder": "http://10.10.10.x:8989", "type": "text"},
        {"key": "SONARR_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "radarr": [
        {"key": "RADARR_URL", "label": "URL", "placeholder": "http://10.10.10.x:7878", "type": "text"},
        {"key": "RADARR_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "prowlarr": [
        {"key": "PROWLARR_URL", "label": "URL", "placeholder": "http://10.10.10.x:9696", "type": "text"},
        {"key": "PROWLARR_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "sabnzbd": [
        {"key": "SABNZBD_URL", "label": "URL", "placeholder": "http://10.10.10.x:8080", "type": "text"},
        {"key": "SABNZBD_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "overseerr": [
        {"key": "OVERSEERR_URL", "label": "URL", "placeholder": "http://10.10.10.x:5055", "type": "text"},
        {"key": "OVERSEERR_API_KEY", "label": "API Key", "placeholder": "", "type": "password"},
    ],
    "smart_health": [
        # Smart health re-uses Proxmox connection — no separate fields, just informational
    ],
    "hyperv": [
        {"key": "HYPERV_HOST",     "label": "Host",     "placeholder": "10.10.10.90",  "type": "text"},
        {"key": "HYPERV_USERNAME", "label": "Username", "placeholder": "administrator", "type": "text"},
        {"key": "HYPERV_PASSWORD", "label": "Password", "placeholder": "",              "type": "password"},
    ],
    "malware_sources": [
        # No credentials needed — public feeds
    ],
}

# Which card types require credentials (used to determine if an integration is "configured")
# Types not in INTEGRATION_FIELDS or with empty fields are always-available (no creds needed)
ALWAYS_AVAILABLE = {"malware_sources", "smart_health"}


def load_config_json() -> dict:
    """Load state/config.json. Returns empty dict if not present."""
    STATE_DIR.mkdir(exist_ok=True)
    if CONFIG_JSON.exists():
        try:
            with open(CONFIG_JSON) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config_json(cfg: dict):
    STATE_DIR.mkdir(exist_ok=True)
    with open(CONFIG_JSON, "w") as f:
        json.dump(cfg, f, indent=2)


# Merge config.json into E on startup so collectors get credentials immediately
_startup_cfg = load_config_json()
if _startup_cfg.get("integrations"):
    for _itype, _ifields in _startup_cfg["integrations"].items():
        if isinstance(_ifields, dict):
            for _k, _v in _ifields.items():
                if _v and str(_v).strip():
                    E[_k] = str(_v).strip()


def _build_integration_env(cfg_json: dict) -> dict:
    """Merge env vars: .env first, config.json wins. Returns merged E dict."""
    merged = dict(E)  # start with .env values
    integrations = cfg_json.get("integrations", {})
    for itype, fields in integrations.items():
        if isinstance(fields, dict):
            for k, v in fields.items():
                if v and v.strip():
                    merged[k] = v.strip()
    return merged


def _is_configured(itype: str, cfg_json: dict) -> bool:
    """True if all required fields for this integration are set (via .env or config.json)."""
    if itype in ALWAYS_AVAILABLE:
        return True
    fields = INTEGRATION_FIELDS.get(itype, [])
    if not fields:
        return True
    merged = _build_integration_env(cfg_json)
    # At minimum, the first non-optional field must be set
    required_fields = [f for f in fields if "optional" not in f.get("label", "").lower()]
    if not required_fields:
        required_fields = fields[:1]
    return all(bool(merged.get(f["key"], "").strip()) for f in required_fields[:1])


def _get_env_for_type(itype: str, cfg_json: dict) -> dict:
    """Get merged env dict for a specific integration type."""
    return _build_integration_env(cfg_json)


@app.get("/api/integrations")
def api_get_integrations():
    """Return all integration type definitions with field specs and current config status."""
    cfg_json = load_config_json()
    merged = _build_integration_env(cfg_json)
    result = {}
    for itype, meta in CARD_TYPE_META.items():
        if itype in ("section_header", "wan_health", "wan_health_sec",
                     "adguard2", "uptime_kuma_detail"):
            continue  # aliases / virtual types
        fields = INTEGRATION_FIELDS.get(itype, [])
        configured = _is_configured(itype, cfg_json)
        # Return current values (masked for passwords)
        current_values = {}
        for field in fields:
            raw = merged.get(field["key"], "")
            if field["type"] == "password" and raw:
                current_values[field["key"]] = "••••••••"
            else:
                current_values[field["key"]] = raw
        result[itype] = {
            "label": meta["label"],
            "description": meta["description"],
            "category": meta["category"],
            "icon": meta["icon"],
            "fields": fields,
            "current_values": current_values,
            "configured": configured,
            "always_available": itype in ALWAYS_AVAILABLE or not fields,
        }
    return result


@app.post("/api/integrations/{itype}")
async def api_save_integration(itype: str, request: Request):
    """Save integration credentials to state/config.json."""
    if itype not in INTEGRATION_FIELDS and itype not in ALWAYS_AVAILABLE:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {itype}")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    # Validate keys are known
    allowed_keys = {f["key"] for f in INTEGRATION_FIELDS.get(itype, [])}
    clean = {}
    for k, v in body.items():
        if k in allowed_keys:
            # Don't overwrite with masked value
            if v and v != "••••••••":
                clean[k] = str(v).strip()
            elif not v:
                clean[k] = ""
    cfg_json = load_config_json()
    integrations = cfg_json.setdefault("integrations", {})
    existing = integrations.get(itype, {})
    existing.update(clean)
    integrations[itype] = existing
    save_config_json(cfg_json)
    # Rebuild the global E dict
    global E
    E = _build_integration_env(cfg_json)
    return {"ok": True, "itype": itype}


@app.delete("/api/integrations/{itype}")
def api_delete_integration(itype: str):
    """Remove integration config from config.json (reverts to .env fallback)."""
    cfg_json = load_config_json()
    cfg_json.get("integrations", {}).pop(itype, None)
    save_config_json(cfg_json)
    global E
    E = _build_integration_env(cfg_json)
    return {"ok": True}


@app.post("/api/integrations/{itype}/test")
async def api_test_integration(itype: str, request: Request):
    """
    Test an integration by running its collector with provided (or saved) credentials.
    Returns {ok: bool, message: str, elapsed: float}.
    Body: same as save — optional field overrides for testing before saving.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    # Build a temporary E dict with body overrides
    cfg_json = load_config_json()
    tmp_E = _build_integration_env(cfg_json)
    allowed_keys = {f["key"] for f in INTEGRATION_FIELDS.get(itype, [])}
    for k, v in body.items():
        if k in allowed_keys and v and v != "••••••••":
            tmp_E[k] = str(v).strip()
    # Run the collector
    cmap = get_collectors()
    # For test, wan_health -> unifi
    effective_type = itype
    if itype == "wan_health":
        effective_type = "unifi"
    fn = cmap.get(effective_type)
    if fn is None:
        # No collector = always available (e.g. malware_sources has a collector but
        # smart_health uses proxmox). Try the actual key.
        fn = cmap.get(itype)
    if fn is None:
        return {"ok": True, "message": "No connection test available for this type.", "elapsed": 0}
    try:
        t0 = time.time()
        data = fn(tmp_E, {})
        elapsed = round(time.time() - t0, 3)
        state = data.get("state", "ok")
        if state in ("error",):
            note = data.get("note", "Collector returned error")
            return {"ok": False, "message": note, "elapsed": elapsed}
        return {"ok": True, "message": f"Connected — state: {state}", "elapsed": elapsed}
    except Exception as e:
        elapsed = round(time.time() - t0, 3)
        return {"ok": False, "message": str(e)[:200], "elapsed": elapsed}


_integration_status_cache: dict = {}
_integration_status_ts: float = 0
_INTEGRATION_STATUS_TTL = 55  # seconds


@app.get("/api/integrations/status")
def api_integration_status():
    """
    Live status of all configured integrations. Cached for 55s (UI refreshes at 60s).
    Returns {itype: {ok: bool, error: str|null, ts: int}}.
    """
    global _integration_status_cache, _integration_status_ts
    now = time.time()
    if now - _integration_status_ts < _INTEGRATION_STATUS_TTL and _integration_status_cache:
        return _integration_status_cache
    cfg_json = load_config_json()
    cmap = get_collectors()
    result = {}
    for itype in INTEGRATION_FIELDS:
        if not _is_configured(itype, cfg_json):
            continue
        # Aliases handled by skipping them; run unique ones
        fn = cmap.get(itype)
        if fn is None:
            continue
        try:
            t0 = time.time()
            data = fn(_build_integration_env(cfg_json), {})
            elapsed = round(time.time() - t0, 3)
            state = data.get("state", "ok")
            if state == "error":
                result[itype] = {"ok": False, "error": data.get("note", "Error"), "elapsed": elapsed, "ts": int(now)}
            else:
                result[itype] = {"ok": True, "error": None, "elapsed": elapsed, "ts": int(now)}
        except Exception as e:
            result[itype] = {"ok": False, "error": str(e)[:120], "elapsed": 0, "ts": int(now)}
    _integration_status_cache = result
    _integration_status_ts = now
    return result


@app.get("/api/first-launch")
def api_first_launch():
    """Return whether this is a first-launch (no integrations configured yet)."""
    cfg_json = load_config_json()
    integrations = cfg_json.get("integrations", {})
    # Count actually-configured integrations
    count = sum(1 for itype in INTEGRATION_FIELDS if _is_configured(itype, cfg_json)
                and itype not in ALWAYS_AVAILABLE)
    return {"first_launch": count == 0, "configured_count": count}



# ── Static file serving (React app) ───────────────────────────────────────────

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(FRONTEND_DIST / "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        file_path = FRONTEND_DIST / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
else:
    @app.get("/")
    def serve_no_frontend():
        return JSONResponse(
            {"error": "Frontend not built. Run: cd frontend && npm run build"},
            status_code=503
        )