#!/usr/bin/env python3
"""
NOC Dashboard Generator
Reads dashboard.yaml, queries all configured data sources, renders index.html.
Zero hardcoded cards — everything is YAML-driven.

Usage:
    python3 generator.py [--config dashboard.yaml] [--env .env] [--theme THEME]
"""

import argparse
import html as _html
import json
import math
import os
import re
import sys
import time
import traceback
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# ── Project root ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "trends.json"
THEMES_DIR = ROOT / "themes"

# ── Env loader ────────────────────────────────────────────────────────────────

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
    # Allow process env to override (useful for Docker)
    for k, v in os.environ.items():
        if k in d or k.isupper():
            d[k] = v
    return d


# ── Theme loader ──────────────────────────────────────────────────────────────

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
    "font_family": "JetBrains Mono, Fira Code, monospace",
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


def load_theme(theme_cfg):
    t = dict(THEME_DEFAULTS)
    preset = (theme_cfg or {}).get("preset", "dark-noc")
    theme_file = THEMES_DIR / f"{preset}.yaml"
    if theme_file.exists():
        with open(theme_file) as f:
            preset_data = yaml.safe_load(f) or {}
        t.update({k: v for k, v in preset_data.items() if k != "name" and k != "description"})
    overrides = (theme_cfg or {}).get("overrides") or {}
    t.update(overrides)
    return t


def load_all_themes():
    themes = {}
    for f in THEMES_DIR.glob("*.yaml"):
        with open(f) as fh:
            data = yaml.safe_load(fh) or {}
        themes[f.stem] = {k: v for k, v in data.items() if k != "name" and k != "description"}
    return themes


# ── Trends / history ──────────────────────────────────────────────────────────

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


def update_trends(data, now_epoch, trends):
    MAX_HOURS = 48
    cutoff = now_epoch - MAX_HOURS * 3600
    mappings = {
        "proxmox": [("cpu", "cpu")],
        "adguard": [("block_pct", "block_pct"), ("queries", "queries")],
        "wazuh": [("alerts_24h", "alerts_24h"), ("high_24h", "high_24h")],
    }
    for key, fields in mappings.items():
        if key not in data:
            continue
        src = data[key]
        if src.get("state") in ("error", "degraded"):
            continue
        for field_name, trend_key in fields:
            val = src.get(field_name)
            if val is None:
                continue
            series_key = f"{key}.{trend_key}"
            series = trends.get(series_key, [])
            series.append([now_epoch, float(val)])
            series = [[t, v] for t, v in series if t >= cutoff]
            trends[series_key] = series
    return trends


# ── Collectors dispatch ────────────────────────────────────────────────────────

def run_collectors(sections, E):
    from collectors import (
        proxmox, wazuh, malware_sources, docker_portainer, pbs, uptime_kuma,
        crowdsec, unifi, adguard, home_assistant, smart_health, urbackup,
        qnap, media, cloudflare, nginx_proxy, tailscale, limacharlie, custom_url
    )

    COLLECTOR_MAP = {
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
        # aliases
        "wan_health": unifi.collect,
    }

    # Deduplicate: only collect each type once even if used in multiple cards
    needed = {}
    for section in sections:
        for card in section.get("cards", []):
            ctype = card.get("type")
            if ctype and ctype not in needed:
                needed[ctype] = card

    results = {}
    errors = {}
    for ctype, card_cfg in needed.items():
        fn = COLLECTOR_MAP.get(ctype)
        if fn is None:
            errors[ctype] = f"no collector for type '{ctype}'"
            results[ctype] = {"state": "degraded", "note": f"unknown card type: {ctype}"}
            continue
        try:
            t0 = time.time()
            results[ctype] = fn(E, card_cfg)
            elapsed = round(time.time() - t0, 2)
            print(f"  [{ctype}] ok ({elapsed}s)", flush=True)
        except Exception as e:
            tb = traceback.format_exc()
            errors[ctype] = f"{type(e).__name__}: {e}"
            results[ctype] = {"state": "error", "note": str(e)[:200]}
            print(f"  [{ctype}] ERROR: {type(e).__name__}: {e}", flush=True)

    return results, errors


# ── HTML rendering helpers ────────────────────────────────────────────────────

def esc(x):
    return _html.escape(str(x)) if x is not None else ""


def state_to_css(state):
    return {
        "ok": "ok",
        "warn": "warn",
        "crit": "crit",
        "error": "error",
        "degraded": "degraded",
    }.get(str(state).lower(), "degraded")


def state_dot(state):
    cls = state_to_css(state)
    return f'<span class="dot dot-{cls}"></span>'


def metric_row(label, value, state=""):
    cls = f" class=\"val-{state_to_css(state)}\"" if state else ""
    return f'<div class="metric"><span class="mlabel">{esc(label)}</span><span class="mval"{cls}>{esc(value)}</span></div>\n'


def badge(text, state="ok"):
    return f'<span class="badge badge-{state_to_css(state)}">{esc(text)}</span>'


def human_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if n < 1024 or unit == "PB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


def sparkline_svg(values, width=140, height=34, color="#00ff41", fill="rgba(0,255,65,0.12)", stroke_width="2"):
    if not values or len(values) < 2:
        return f'<svg width="{width}" height="{height}"><text x="4" y="20" fill="#555" font-size="10">collecting...</text></svg>'
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    pad = 2
    pts = []
    for i, v in enumerate(values):
        x = pad + (i / (len(values) - 1)) * (width - 2 * pad)
        y = pad + (1 - (v - mn) / rng) * (height - 2 * pad)
        pts.append((x, y))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    fill_path = (f"M{pts[0][0]:.1f},{height} " +
                 " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts) +
                 f" L{pts[-1][0]:.1f},{height} Z")
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<path d="{fill_path}" fill="{fill}" />'
            f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="{stroke_width}" stroke-linejoin="round" stroke-linecap="round"/>'
            f'</svg>')


def donut_svg(pct, color_ok="#00ff41", color_warn="#ffaa00", color_crit="#ff3333",
              track="#1a1a1a", size=60, stroke=8):
    r = (size - stroke) / 2
    circ = 2 * math.pi * r
    dash = (pct / 100) * circ
    gap = circ - dash
    color = color_ok if pct < 75 else (color_warn if pct < 90 else color_crit)
    cx = cy = size / 2
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{track}" stroke-width="{stroke}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke}"'
            f' stroke-dasharray="{dash:.1f} {gap:.1f}" stroke-linecap="round"'
            f' transform="rotate(-90 {cx} {cy})"/>'
            f'<text x="{cx}" y="{cy + 4}" text-anchor="middle" font-size="12" fill="{color}">{pct:.0f}%</text>'
            f'</svg>')


def heatmap_svg(status_map, now_epoch, hours=24, width=280, height=20):
    """24h uptime heatmap — green/red blocks per slot."""
    n = 48
    slot_sec = (hours * 3600) // n
    w = width // n
    slots = []
    for i in range(n):
        t_start = now_epoch - (n - i) * slot_sec
        t_end = t_start + slot_sec
        slots.append((t_start, t_end))
    items = list((status_map or {}).items())
    svg = f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    for i, (ts, te) in enumerate(slots):
        x = i * w
        color = "#00ff41"
        svg += f'<rect x="{x}" y="0" width="{w-1}" height="{height}" fill="{color}" rx="1"/>'
    svg += '</svg>'
    return svg


def kuma_heatmap(status_map, width=280, height=16):
    """Simple row of colored blocks for Uptime Kuma monitors."""
    items = sorted((status_map or {}).items())
    if not items:
        return '<span style="color:#555">no data</span>'
    bw = max(8, min(24, width // max(len(items), 1)))
    svg = f'<svg width="{len(items)*bw}" height="{height}">'
    for i, (name, status) in enumerate(items):
        color = "#00ff41" if status == 1 else ("#ff3333" if status == 0 else "#ffaa00")
        svg += f'<rect x="{i*bw}" y="0" width="{bw-1}" height="{height}" fill="{color}" rx="2"><title>{esc(name)}</title></rect>'
    svg += '</svg>'
    return svg


# ── Card renderers ────────────────────────────────────────────────────────────

def render_card(card_cfg, data, trends, theme, now_epoch):
    ctype = card_cfg.get("type", "unknown")
    title = card_cfg.get("title", ctype.upper())
    size = card_cfg.get("size", "normal")
    notes = card_cfg.get("notes", "")

    d = data.get(ctype, {"state": "degraded", "note": "not collected"})
    state = d.get("state", "degraded")
    show = card_cfg.get("show", [])

    body = ""
    try:
        renderer = CARD_RENDERERS.get(ctype, render_generic)
        body = renderer(d, card_cfg, trends, theme, now_epoch)
    except Exception as e:
        body = f'<div class="card-error">render error: {esc(str(e)[:120])}</div>'

    # Graph
    graph_html = ""
    if card_cfg.get("graph"):
        graph_html = render_graph(card_cfg, d, trends, theme)

    note_html = f'<div class="card-note">{esc(notes)}</div>' if notes else ""
    err_note = d.get("note", "")
    if err_note and state in ("error", "degraded"):
        note_html += f'<div class="card-note card-note-err">{esc(err_note)}</div>'

    size_class = {"normal": "", "wide": "card-wide", "tall": "card-tall", "large": "card-large"}.get(size, "")
    return (f'<div class="card {size_class} state-{state_to_css(state)}">'
            f'<div class="card-header">{state_dot(state)}<span class="card-title">{esc(title)}</span></div>'
            f'<div class="card-body">{body}{graph_html}</div>'
            f'{note_html}'
            f'</div>\n')


def render_graph(card_cfg, d, trends, theme):
    graph_type = card_cfg.get("graph_type", "sparkline")
    graph_field = card_cfg.get("graph_field", "")
    ctype = card_cfg.get("type", "")
    series_key = f"{ctype}.{graph_field}" if graph_field else ""
    color = card_cfg.get("graph_color", theme.get("graph_line_color", "#00ff41"))
    fill = theme.get("graph_fill_color", "rgba(0,255,65,0.12)")
    stroke_w = theme.get("sparkline_stroke_width", "2")

    if graph_type == "donut":
        storage = d.get("storage", [])
        if not storage:
            return ""
        html = '<div class="donuts">'
        for s in storage[:6]:
            html += (f'<div class="donut-wrap">'
                     f'{donut_svg(s["pct"], theme["gauge_fill_ok"], theme["gauge_fill_warn"], theme["gauge_fill_critical"], theme["gauge_track_color"])}'
                     f'<div class="donut-label">{esc(s["name"])}</div>'
                     f'</div>')
        html += '</div>'
        return html

    if series_key and series_key in trends:
        values = [v for _, v in trends[series_key][-60:]]
    elif graph_field and graph_field in d:
        values = [float(d[graph_field])]
    else:
        values = []

    if graph_type == "sparkline":
        return f'<div class="sparkline">{sparkline_svg(values, 180, 34, color, fill, stroke_w)}</div>'
    elif graph_type == "area":
        return f'<div class="sparkline">{sparkline_svg(values, 180, 50, color, fill, stroke_w)}</div>'
    elif graph_type == "gauge":
        pct = float(d.get(graph_field, 0) or 0)
        return donut_svg(pct, theme["gauge_fill_ok"], theme["gauge_fill_warn"], theme["gauge_fill_critical"], theme["gauge_track_color"], 70, 10)

    return f'<div class="sparkline">{sparkline_svg(values, 180, 34, color, fill, stroke_w)}</div>'


# ── Per-type card body renderers ──────────────────────────────────────────────

def render_proxmox(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("VMs", f"{d.get('vms_running', 0)} / {d.get('vms_total', 0)} running",
                      "ok" if not d.get("down_vms") else "warn")
    out += metric_row("CPU", f"{d.get('cpu', 0):.1f}%",
                      "crit" if d.get("cpu", 0) >= 90 else "warn" if d.get("cpu", 0) >= 75 else "ok")
    mem_u, mem_t = d.get("mem_used", 0), d.get("mem_total", 1)
    mem_pct = round(100 * mem_u / mem_t, 1) if mem_t else 0
    out += metric_row("RAM", f"{mem_u:.1f} / {mem_t:.1f} GB ({mem_pct}%)",
                      "crit" if mem_pct >= 90 else "warn" if mem_pct >= 80 else "ok")
    out += metric_row("Uptime", f"{d.get('uptime_d', 0)}d")
    storage = d.get("storage", [])
    for s in storage[:4]:
        out += metric_row(f"  {s['name']}", f"{s['pct']}%",
                          "crit" if s["pct"] >= 90 else "warn" if s["pct"] >= 80 else "ok")
    down = d.get("down_vms", [])
    if down:
        out += f'<div class="sublist warn-text">DOWN: {esc(", ".join(down[:5]))}</div>'
    return out


def render_docker(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Running", f"{d.get('running', 0)} / {d.get('total', 0)}",
                      "ok" if not d.get("bad") else "warn")
    out += metric_row("Envs", str(d.get("envs", 0)))
    bad = d.get("bad", [])
    if bad:
        out += '<div class="sublist warn-text">'
        for b in bad[:6]:
            out += f'{esc(b)}<br>'
        out += '</div>'
    return out


def render_pbs(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Tasks 24h", f"OK:{d.get('ok', 0)}  Fail:{d.get('fail', 0)}  Run:{d.get('run', 0)}",
                      "crit" if d.get("fail") else "ok")
    out += metric_row("Last Backup", d.get("last_backup", "?"),
                      "warn" if "ago" not in str(d.get("last_backup", "")) else "ok")
    for ds in d.get("datastores", []):
        out += metric_row(f"  {ds['name']}", f"{ds['pct']}%",
                          "crit" if ds["pct"] >= 90 else "warn" if ds["pct"] >= 80 else "ok")
    return out


def render_urbackup(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Clients", f"{d.get('online', 0)} / {d.get('total', 0)} online",
                      "warn" if d.get("online", 0) < d.get("total", 0) else "ok")
    for c in d.get("clients", [])[:6]:
        state = c.get("state", "ok")
        out += metric_row(f"  {c['name']}", f"{c['ago']} {'online' if c['online'] else 'OFFLINE'}",
                          state)
    return out


def render_uptime_kuma(d, cfg, trends, theme, now_epoch):
    out = ""
    total = d.get("total", 0)
    up = d.get("up", 0)
    down = d.get("down", [])
    out += metric_row("Monitors", f"{up} / {total} up",
                      "crit" if down else "ok")
    # heatmap of all monitors
    status_map = d.get("status_map", {})
    if status_map:
        out += f'<div class="kuma-heatmap">{kuma_heatmap(status_map, 300)}</div>'
    if down:
        out += f'<div class="sublist warn-text">DOWN: {esc(", ".join(down[:8]))}</div>'
    # cert expiry
    certs = [c for c in d.get("certs", []) if c["days"] <= 60][:4]
    if certs:
        out += '<div class="sublist">'
        for c in certs:
            state = "crit" if c["days"] <= 7 else "warn" if c["days"] <= 30 else "ok"
            out += f'<div class="metric"><span class="mlabel">{esc(c["name"][:28])}</span><span class="mval val-{state}">{c["days"]}d</span></div>'
        out += '</div>'
    return out


def render_home_assistant(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Entities", f"{d.get('entities', 0)} ({d.get('domains', 0)} domains)")
    out += metric_row("Alerts", str(d.get("alerts_on", 0)),
                      "crit" if d.get("alerts_on") else "ok")
    out += metric_row("Notifications", str(d.get("notifications", 0)),
                      "warn" if d.get("notifications") else "ok")
    out += metric_row("Unavailable", str(d.get("unavailable", 0)),
                      "warn" if d.get("unavailable", 0) > 5 else "ok")
    for name in d.get("alert_names", [])[:4]:
        out += f'<div class="sublist warn-text">{esc(name)}</div>'
    return out


def render_smart_health(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Disks", f"{d.get('passed', 0)} passed / {d.get('checked', 0)} checked",
                      "crit" if d.get("fail") else "warn" if d.get("warn") else "ok")
    for prob in d.get("problems", [])[:4]:
        out += f'<div class="sublist warn-text">{esc(prob[:60])}</div>'
    if d.get("vm_disks"):
        out += f'<div class="card-note">{d["vm_disks"]} VM virtual disk(s) not exposed</div>'
    return out


def render_wazuh(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Agents", f"{d.get('active', 0)} / {d.get('total', 0)} active",
                      "warn" if d.get("down") else "ok")
    if "alerts_24h" in d:
        out += metric_row("Alerts 24h", str(d.get("alerts_24h", 0)))
    if "high_24h" in d:
        out += metric_row("High (lvl≥12)", str(d.get("high_24h", 0)),
                          "crit" if d.get("high_24h") else "ok")
    if d.get("down"):
        out += f'<div class="sublist warn-text">DOWN: {esc(", ".join(d["down"][:4]))}</div>'
    return out


def render_malware_sources(d, cfg, trends, theme, now_epoch):
    out = ""
    for src, info in d.get("sources", {}).items():
        if not info.get("live"):
            out += metric_row(src.upper(), "—", "degraded")
        else:
            cnt = info.get("count")
            val = str(cnt) if cnt is not None else "?"
            state = "warn" if (cnt and cnt > 0) else "ok"
            out += metric_row(src.upper(), val + " 24h", state)
    return out


def render_crowdsec(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Total Bans", str(d.get("bans", 0)))
    out += metric_row("Local Bans", str(d.get("local_bans", 0)))
    if d.get("detections_24h") is not None:
        out += metric_row("Detections 24h", str(d["detections_24h"]),
                          "warn" if d["detections_24h"] > 0 else "ok")
    for k, v in d.get("top", []):
        out += metric_row(f"  {k}", str(v))
    return out


def render_cloudflare(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Requests Today", f"{d.get('requests', 0):,}")
    out += metric_row("Threats Today", str(d.get("threats", 0)),
                      "warn" if d.get("threats") else "ok")
    out += metric_row("Bandwidth", human_bytes(d.get("bytes", 0)))
    if d.get("waf_events") is not None:
        out += metric_row("WAF Events 24h", str(d["waf_events"]))
        out += metric_row("WAF Blocked", str(d.get("waf_blocked", 0)),
                          "warn" if d.get("waf_blocked") else "ok")
    if d.get("waf_note"):
        out += f'<div class="card-note">{esc(d["waf_note"])}</div>'
    return out


def render_unifi(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("WAN", d.get("wan", "?"),
                      "ok" if d.get("wan") == "ok" else "crit")
    out += metric_row("Clients", str(d.get("clients", 0)))
    if d.get("latency") is not None:
        out += metric_row("Latency", f"{d['latency']}ms")
    if d.get("down_mbps") is not None and d.get("up_mbps") is not None:
        out += metric_row("Throughput", f"↓{d['down_mbps']:.0f} ↑{d['up_mbps']:.0f} Mbps")
    out += metric_row("IPS Alerts 24h", str(d.get("ips_24h", 0)),
                      "warn" if d.get("ips_24h", 0) > 0 else "ok")
    if d.get("month_total") is not None:
        out += metric_row("Month Usage", human_bytes(d["month_total"]))
    pia = d.get("pia")
    if pia:
        connected = pia.get("connected", False)
        out += metric_row(f"VPN ({pia.get('name', 'PIA')})",
                          "connected" if connected else "disconnected",
                          "ok" if connected else "warn")
    ssids = d.get("ssids", [])
    if ssids:
        out += '<div class="sublist">'
        for s in ssids[:4]:
            out += f'<div class="metric"><span class="mlabel ssid">{esc(s["name"])}</span><span class="mval">{s["clients"]} clients</span></div>'
        out += '</div>'
    devices = d.get("devices", [])
    if devices:
        out += '<div class="sublist">'
        for dev in devices[:5]:
            state = "ok" if dev["online"] else "warn"
            out += f'<div class="metric"><span class="mlabel">{esc(dev["name"])}</span><span class="mval val-{state}">{esc(dev["uptime"])}</span></div>'
        out += '</div>'
    return out


def render_tailscale(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Devices", f"{d.get('online', 0)} / {d.get('total', 0)} online",
                      "warn" if d.get("offline", 0) > 0 else "ok")
    if d.get("exit_nodes"):
        out += metric_row("Exit Nodes", ", ".join(d["exit_nodes"][:3]))
    if d.get("soonest_expiry_days") is not None:
        days = d["soonest_expiry_days"]
        out += metric_row("Key Expiry", f"{days}d",
                          "crit" if days <= 7 else "warn" if days <= 30 else "ok")
    for dev in d.get("devices", [])[:6]:
        state = "ok" if dev["online"] else "warn"
        out += f'<div class="metric"><span class="mlabel">{esc(dev["name"])}</span><span class="mval val-{state}">{"online" if dev["online"] else "offline"}</span></div>'
    return out


def render_nginx_proxy(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Hosts", f"{d.get('enabled', 0)} enabled / {d.get('hosts', 0)} total",
                      "warn" if d.get("disabled") else "ok")
    out += metric_row("Certs", str(d.get("certs", 0)))
    if d.get("certs_expiring"):
        out += metric_row("Expiring Soon", str(d["certs_expiring"]), "warn")
    for prob in d.get("problems", [])[:4]:
        out += f'<div class="sublist warn-text">{esc(prob[:60])}</div>'
    for cert in d.get("cert_list", [])[:3]:
        state = "crit" if cert["days"] <= 7 else "warn" if cert["days"] <= 14 else "ok"
        out += metric_row(f"  {cert['name'][:28]}", f"{cert['days']}d", state)
    return out


def render_adguard(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Queries", f"{d.get('queries', 0):,}")
    out += metric_row("Blocked", f"{d.get('blocked', 0):,} ({d.get('block_pct', 0):.1f}%)")
    out += metric_row("Avg Latency", f"{d.get('avg_ms', 0):.1f}ms")
    return out


def render_qnap(d, cfg, trends, theme, now_epoch):
    out = ""
    for unit in d.get("units", []):
        label = unit.get("label", "?")
        state = unit.get("state", "ok")
        out += f'<div class="subheader">{esc(label)} — {esc(unit.get("host", unit.get("ip", "?")))}</div>'
        if state in ("error", "degraded"):
            out += f'<div class="card-note card-note-err">{esc(unit.get("error") or unit.get("note", "error"))}</div>'
            continue
        for vol in unit.get("volumes", [])[:3]:
            vstate = "crit" if vol["pct"] >= 90 else "warn" if vol["pct"] >= 80 else "ok"
            out += metric_row(f"  {vol['name']}", f"{vol['used_t']:.1f} / {vol['total_t']:.1f}T ({vol['pct']}%)", vstate)
        for disk in unit.get("disks", [])[:4]:
            h = str(disk.get("health", "?")).upper()
            tc = disk.get("temp")
            val = h + (f" {tc}C" if tc is not None else "")
            dstate = "ok" if h in ("OK", "GOOD", "NORMAL") else "crit"
            out += metric_row(f"  {disk['alias']}", val, dstate)
        if unit.get("sys_temp") is not None:
            out += metric_row("  Temp", f"{unit['sys_temp']}C",
                              "warn" if unit["sys_temp"] >= 55 else "ok")
    return out


def render_proxmox_storage(d, cfg, trends, theme, now_epoch):
    out = ""
    for s in d.get("storage", []):
        state = "crit" if s["pct"] >= 90 else "warn" if s["pct"] >= 80 else "ok"
        out += metric_row(s["name"], f"{s['used_g']:.0f} / {s['total_g']:.0f}G ({s['pct']}%)", state)
    return out


def render_plex(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Active Streams", str(d.get("streams", 0)),
                      "warn" if d.get("streams", 0) > 5 else "ok")
    out += metric_row("Movies", f"{d.get('movies', 0):,}")
    out += metric_row("Shows", f"{d.get('shows', 0):,}")
    return out


def render_tautulli(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Streams Now", str(d.get("streams", 0)))
    out += metric_row("Plays Today", str(d.get("plays_today", 0)))
    if d.get("top_user"):
        out += metric_row("Top User", f"{d['top_user']} ({d.get('top_plays', 0)})")
    return out


def render_sonarr(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Series", f"{d.get('monitored', 0)} monitored / {d.get('total', 0)}")
    out += metric_row("Queue", str(d.get("queue", 0)), "warn" if d.get("queue") else "ok")
    out += metric_row("Missing", str(d.get("missing", 0)), "warn" if d.get("missing") else "ok")
    return out


def render_radarr(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Movies", f"{d.get('monitored', 0)} monitored / {d.get('total', 0)}")
    out += metric_row("Queue", str(d.get("queue", 0)), "warn" if d.get("queue") else "ok")
    out += metric_row("Missing", str(d.get("missing", 0)), "warn" if d.get("missing") else "ok")
    return out


def render_prowlarr(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Indexers", f"{d.get('healthy', 0)} healthy / {d.get('enabled', 0)} enabled")
    out += metric_row("Failing", str(d.get("failing", 0)), "warn" if d.get("failing") else "ok")
    return out


def render_sabnzbd(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Status", d.get("status", "?"), "warn" if d.get("status", "").lower() == "paused" else "ok")
    out += metric_row("Queue", f"{d.get('slots', 0)} items")
    if float(d.get("speed_mbps", 0) or 0) > 0:
        out += metric_row("Speed", f"{d.get('speed_mbps', 0):.1f} MB/s")
    out += metric_row("Downloaded Today", f"{d.get('day_gb', 0):.2f} GB")
    return out


def render_overseerr(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Pending", str(d.get("pending", 0)), "warn" if d.get("pending") else "ok")
    out += metric_row("Approved", str(d.get("approved", 0)))
    out += metric_row("Available", str(d.get("available", 0)))
    out += metric_row("Total Requests", str(d.get("total", 0)))
    return out


def render_limacharlie(d, cfg, trends, theme, now_epoch):
    out = ""
    out += metric_row("Sensors", f"{d.get('online', 0)} online / {d.get('total', 0)} total",
                      "warn" if d.get("offline", 0) > 0 else "ok")
    if d.get("detections_24h") is not None:
        out += metric_row("Detections 24h", str(d["detections_24h"]),
                          "warn" if d.get("detections_24h", 0) > 0 else "ok")
    for k, v in d.get("top", []):
        out += metric_row(f"  {k}", str(v))
    if d.get("offline_hosts"):
        out += f'<div class="sublist warn-text">Offline: {esc(", ".join(d["offline_hosts"]))}</div>'
    return out


def render_custom_url(d, cfg, trends, theme, now_epoch):
    out = ""
    for name, val in d.get("values", {}).items():
        out += metric_row(name, str(val) if val is not None else "null")
    return out


def render_generic(d, cfg, trends, theme, now_epoch):
    out = ""
    for k, v in d.items():
        if k in ("state", "note"):
            continue
        if isinstance(v, (dict, list)):
            continue
        out += metric_row(k, str(v))
    return out


CARD_RENDERERS = {
    "proxmox": render_proxmox,
    "proxmox_storage": render_proxmox_storage,
    "docker": render_docker,
    "pbs": render_pbs,
    "urbackup": render_urbackup,
    "uptime_kuma": render_uptime_kuma,
    "home_assistant": render_home_assistant,
    "smart_health": render_smart_health,
    "wazuh": render_wazuh,
    "malware_sources": render_malware_sources,
    "crowdsec": render_crowdsec,
    "cloudflare": render_cloudflare,
    "unifi": render_unifi,
    "tailscale": render_tailscale,
    "nginx_proxy": render_nginx_proxy,
    "adguard": render_adguard,
    "qnap": render_qnap,
    "plex": render_plex,
    "tautulli": render_tautulli,
    "sonarr": render_sonarr,
    "radarr": render_radarr,
    "prowlarr": render_prowlarr,
    "sabnzbd": render_sabnzbd,
    "overseerr": render_overseerr,
    "limacharlie": render_limacharlie,
    "custom_url": render_custom_url,
    "wan_health": render_unifi,
}


# ── CSS generator ─────────────────────────────────────────────────────────────

def build_css(t, all_themes):
    """Generate CSS with all theme variables and auto-switch support."""
    # Build per-theme variables
    theme_blocks = ""
    for name, td in all_themes.items():
        merged = dict(THEME_DEFAULTS)
        merged.update(td)
        vars_str = ""
        for k, v in merged.items():
            vars_str += f"  --{k.replace('_', '-')}: {v};\n"
        theme_blocks += f"\n[data-theme='{name}'] {{\n{vars_str}}}\n"

    base_vars = ""
    for k, v in t.items():
        base_vars += f"  --{k.replace('_', '-')}: {v};\n"

    return f"""
:root {{
{base_vars}}}
{theme_blocks}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  background: var(--background);
  color: var(--text-primary);
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  min-height: 100vh;
}}

/* ── TOP BAR ── */
.topbar {{
  background: var(--top-bar-background);
  border-bottom: 1px solid var(--top-bar-border);
  padding: 12px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}}
.topbar-title {{
  font-family: var(--heading-font);
  font-size: 18px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 2px;
  text-transform: uppercase;
}}
.topbar-subtitle {{
  color: var(--text-secondary);
  font-size: 12px;
  letter-spacing: 1px;
}}
.topbar-spacer {{ flex: 1; }}
.topbar-status {{ font-size: 12px; color: var(--text-muted); }}
.topbar-updated {{ font-size: 11px; color: var(--text-muted); }}
.topbar-overall {{ font-size: 13px; font-weight: bold; }}
.topbar-overall.ok {{ color: var(--ok-color); }}
.topbar-overall.warn {{ color: var(--warn-color); }}
.topbar-overall.crit {{ color: var(--error-color); }}

/* Theme toggle button */
.theme-toggle {{
  background: none;
  border: 1px solid var(--card-border);
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-family: var(--font-family);
}}
.theme-toggle:hover {{ border-color: var(--accent); color: var(--accent); }}

/* ── LAYOUT ── */
.dashboard {{
  padding: 16px 20px;
}}

.section {{
  margin-bottom: 24px;
}}
.section-header {{
  color: var(--section-header-color);
  font-family: var(--heading-font);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 3px;
  text-transform: uppercase;
  padding: 6px 0;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--card-border);
}}

/* Grid */
.cards {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}}
@media (max-width: 1200px) {{ .cards {{ grid-template-columns: repeat(3, 1fr); }} }}
@media (max-width: 900px)  {{ .cards {{ grid-template-columns: repeat(2, 1fr); }} }}
@media (max-width: 600px)  {{ .cards {{ grid-template-columns: 1fr; }} }}

/* ── CARDS ── */
.card {{
  background: var(--card-background);
  border: 1px solid var(--card-border);
  border-radius: var(--card-border-radius);
  box-shadow: var(--card-shadow);
  display: flex;
  flex-direction: column;
  transition: border-color 0.2s;
  min-height: 100px;
}}
.card-wide {{ grid-column: span 2; }}
.card-tall {{ grid-row: span 2; }}
.card-large {{ grid-column: span 2; grid-row: span 2; }}

.card.state-ok    {{ border-left: 3px solid var(--ok-color); }}
.card.state-warn  {{ border-left: 3px solid var(--warn-color); }}
.card.state-crit  {{ border-left: 3px solid var(--error-color); }}
.card.state-error {{ border-left: 3px solid var(--error-color); opacity: 0.8; }}
.card.state-degraded {{ border-left: 3px solid var(--text-muted); opacity: 0.8; }}

.card-header {{
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px 6px;
  border-bottom: 1px solid var(--card-border);
}}
.card-title {{
  font-family: var(--heading-font);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--text-secondary);
}}

.card-body {{
  padding: 8px 12px;
  flex: 1;
}}

/* Status dot */
.dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}}
.dot-ok       {{ background: var(--ok-color); box-shadow: 0 0 4px var(--ok-color); }}
.dot-warn     {{ background: var(--warn-color); box-shadow: 0 0 4px var(--warn-color); }}
.dot-crit     {{ background: var(--error-color); box-shadow: 0 0 4px var(--error-color); animation: blink 1s step-end infinite; }}
.dot-error    {{ background: var(--error-color); }}
.dot-degraded {{ background: var(--text-muted); }}

@keyframes blink {{
  0%, 100% {{ opacity: 1; }}
  50%      {{ opacity: 0.3; }}
}}

/* Metrics */
.metric {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 0;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}}
.mlabel {{
  color: var(--text-secondary);
  font-size: 11px;
  min-width: 90px;
  padding-right: 8px;
}}
.mval {{
  color: var(--text-primary);
  font-size: 12px;
  text-align: right;
}}

.val-ok       {{ color: var(--ok-color); }}
.val-warn     {{ color: var(--warn-color); }}
.val-crit     {{ color: var(--error-color); }}
.val-error    {{ color: var(--error-color); }}
.val-degraded {{ color: var(--text-muted); }}

.sublist {{
  margin-top: 4px;
  padding: 4px 6px;
  background: rgba(0,0,0,0.15);
  border-radius: 3px;
  font-size: 11px;
  color: var(--text-secondary);
}}
.warn-text {{ color: var(--warn-color); }}
.subheader {{
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--accent-secondary);
  margin: 6px 0 2px;
}}

.card-note {{
  font-size: 10px;
  color: var(--text-muted);
  padding: 4px 12px;
  border-top: 1px solid var(--card-border);
}}
.card-note-err {{ color: var(--warn-color); }}
.card-error {{ color: var(--error-color); font-size: 11px; padding: 4px 0; }}

.badge {{
  display: inline-block;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}}
.badge-ok       {{ background: rgba(0,255,65,0.15); color: var(--ok-color); }}
.badge-warn     {{ background: rgba(255,170,0,0.15); color: var(--warn-color); }}
.badge-crit     {{ background: rgba(255,51,51,0.15); color: var(--error-color); }}
.badge-degraded {{ background: rgba(100,100,100,0.15); color: var(--text-muted); }}

/* Graphs */
.sparkline {{
  margin-top: 6px;
  overflow: hidden;
}}
.donuts {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}}
.donut-wrap {{
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}}
.donut-label {{
  font-size: 9px;
  color: var(--text-muted);
  text-align: center;
  max-width: 64px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.kuma-heatmap {{
  margin: 6px 0 2px;
  overflow: hidden;
}}
.ssid {{ font-style: italic; }}

/* Footer */
.footer {{
  text-align: center;
  color: var(--text-muted);
  font-size: 10px;
  padding: 20px;
  border-top: 1px solid var(--card-border);
  margin-top: 16px;
}}
"""


# ── Full page renderer ────────────────────────────────────────────────────────

def render_page(cfg, data, trends, theme, all_themes, now_epoch, errors):
    top_bar = cfg.get("top_bar", {})
    theme_cfg = cfg.get("theme", {})
    sections = cfg.get("sections", [])
    refresh_sec = cfg.get("refresh_seconds", 60)

    # Overall status
    all_states = [d.get("state", "degraded") for d in data.values()]
    order = {"ok": 0, "degraded": 1, "warn": 2, "crit": 3, "error": 3}
    overall_state = max(all_states, key=lambda s: order.get(s, 0), default="ok")

    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_epoch))

    # Build sections HTML
    sections_html = ""
    for section in sections:
        section_name = section.get("name", "")
        cards_html = ""
        for card_cfg in section.get("cards", []):
            cards_html += render_card(card_cfg, data, trends, theme, now_epoch)
        sections_html += (f'<div class="section">'
                          f'<div class="section-header">{esc(section_name)}</div>'
                          f'<div class="cards">{cards_html}</div>'
                          f'</div>\n')

    # Topbar
    title = esc(top_bar.get("title", "NOC Dashboard"))
    subtitle = esc(top_bar.get("subtitle", ""))
    show_toggle = top_bar.get("show_theme_toggle", True)
    toggle_html = ('<button class="theme-toggle" onclick="toggleTheme()" title="Toggle theme">◑</button>'
                   if show_toggle else "")
    overall_html = ""
    if top_bar.get("show_overall_status", True):
        overall_icon = {"ok": "●", "warn": "▲", "crit": "✖", "error": "✖", "degraded": "○"}.get(overall_state, "○")
        overall_html = f'<span class="topbar-overall {overall_state}">{overall_icon} {overall_state.upper()}</span>'
    updated_html = f'<span class="topbar-updated">Updated: {ts}</span>' if top_bar.get("show_updated", True) else ""

    # Auto-switch JS
    auto_switch_js = ""
    if theme_cfg.get("auto_switch"):
        day_theme = theme_cfg.get("day_theme", "light-clean")
        night_theme = theme_cfg.get("night_theme", "dark-noc")
        day_start = theme_cfg.get("day_start", "07:00")
        night_start = theme_cfg.get("night_start", "19:00")
        auto_switch_js = f"""
        function autoTheme() {{
            var h = new Date().getHours(), m = new Date().getMinutes();
            var now = h * 60 + m;
            var day = {int(day_start.split(':')[0]) * 60 + int(day_start.split(':')[1])};
            var night = {int(night_start.split(':')[0]) * 60 + int(night_start.split(':')[1])};
            if (!localStorage.getItem('theme-override')) {{
                if (now >= day && now < night) {{
                    document.documentElement.setAttribute('data-theme', '{day_theme}');
                }} else {{
                    document.documentElement.setAttribute('data-theme', '{night_theme}');
                }}
            }}
        }}
        autoTheme();
        setInterval(autoTheme, 60000);
"""

    preset = theme_cfg.get("preset", "dark-noc")
    css = build_css(theme, all_themes)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="{preset}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta http-equiv="refresh" content="{refresh_sec}">
<style>
{css}
</style>
</head>
<body>
<header class="topbar">
  <div>
    <div class="topbar-title">{title}</div>
    {f'<div class="topbar-subtitle">{subtitle}</div>' if subtitle else ''}
  </div>
  <div class="topbar-spacer"></div>
  {overall_html}
  {updated_html}
  {toggle_html}
</header>
<main class="dashboard">
{sections_html}
</main>
<footer class="footer">
  NOC Dashboard &mdash; <a href="https://github.com/mdziegiel/noc-dashboard" style="color:var(--text-muted)">github.com/mdziegiel/noc-dashboard</a>
  &mdash; {len(errors)} error(s) &mdash; Generated {ts}
</footer>
<script>
(function() {{
  {auto_switch_js}

  function toggleTheme() {{
    var cur = document.documentElement.getAttribute('data-theme') || '{preset}';
    var themes = {json.dumps(list(all_themes.keys()))};
    var idx = themes.indexOf(cur);
    var next = themes[(idx + 1) % themes.length];
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme-override', next);
    localStorage.setItem('theme-current', next);
  }}
  window.toggleTheme = toggleTheme;

  // Restore saved theme on load
  var saved = localStorage.getItem('theme-override');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
}})();
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NOC Dashboard Generator")
    parser.add_argument("--config", default=str(ROOT / "dashboard.yaml"))
    parser.add_argument("--env", default=str(Path.home() / ".hermes" / ".env"))
    parser.add_argument("--theme", default=None, help="Override theme preset")
    parser.add_argument("--output", default=None, help="Override output HTML path")
    args = parser.parse_args()

    print(f"NOC Dashboard Generator", flush=True)
    print(f"  Config: {args.config}", flush=True)
    print(f"  Env:    {args.env}", flush=True)

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    E = load_env(args.env)

    theme_cfg = cfg.get("theme", {})
    if args.theme:
        theme_cfg["preset"] = args.theme

    theme = load_theme(theme_cfg)
    all_themes = load_all_themes()

    out_cfg = cfg.get("output", {})
    out_dir = Path(args.output).parent if args.output else Path(out_cfg.get("dir", "./output"))
    out_file = Path(args.output) if args.output else out_dir / out_cfg.get("file", "index.html")
    out_dir.mkdir(parents=True, exist_ok=True)

    now_epoch = time.time()
    trends = load_trends()

    print("Collecting data...", flush=True)
    data, errors = run_collectors(cfg.get("sections", []), E)

    trends = update_trends(data, now_epoch, trends)
    save_trends(trends)

    print("Rendering HTML...", flush=True)
    html = render_page(cfg, data, trends, theme, all_themes, now_epoch, errors)

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Written: {out_file} ({len(html):,} bytes)", flush=True)
    if errors:
        print(f"  Errors: {', '.join(errors.keys())}", flush=True)
    print("Done.", flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
