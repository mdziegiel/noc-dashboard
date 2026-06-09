# NOC Dashboard

**A YAML-configurable, themeable, Docker-ready NOC dashboard generator for self-hosted homelabs.**

Deploy it, edit one YAML file, and get a fully-working live NOC dashboard — no code changes ever needed.

---

![NOC Dashboard — Dark Theme](screenshots/dark-noc.png)

*Dark NOC theme — real MRDTech homelab data*

---

![NOC Dashboard — Light Clean Theme](screenshots/light-clean.png)

*Light Clean theme — same data, professional corporate look*

---

## Features

- **100% YAML-driven** — cards, layout, sections, colors, graphs, and themes all defined in `dashboard.yaml`. Zero code editing to customize.
- **25 card types** — Proxmox, Docker/Portainer, PBS, Wazuh SIEM, CrowdSec, UniFi, Cloudflare, AdGuard, Tailscale, Uptime Kuma, Home Assistant, QNAP, Plex, Sonarr, Radarr, and more.
- **6 built-in themes** — `dark-noc`, `light-clean`, `midnight-blue`, `solarized-dark`, `dracula`, `nord`.
- **Automatic day/night switching** — browser-side JS swaps theme at configured times.
- **Manual theme toggle** — one-click toggle button cycles through all themes.
- **Graph support** — sparkline, area, gauge, donut, and heatmap charts per card.
- **Card sizes** — normal, wide (2×), tall (×2), large (2×2) — CSS grid layout.
- **Trend history** — persisted in `state/trends.json`, sparklines fill in over time.
- **Graceful degradation** — one failed data source never kills the page. Degraded cards render with grey status and an error note.
- **Docker-ready** — `docker-compose up -d` and it runs. Generator on a configurable cron interval + lightweight HTTP server.
- **Read-only** — every query is read-only. No mutations, no side effects.

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/mdziegiel/noc-dashboard.git
cd noc-dashboard
cp .env.example .env
# Edit .env with your real credentials
nano .env
```

### 2. Edit dashboard.yaml

```bash
nano dashboard.yaml
# Set your title, sections, and card types
```

### 3. Run with Docker

```bash
docker-compose up -d
# Dashboard available at http://your-host:8081
```

### 4. Run directly (Python 3.10+)

```bash
pip install -r requirements.txt
python3 generator.py --config dashboard.yaml --env .env
# Serves the generated output/index.html — open it in your browser
# Or serve it:
cd output && python3 -m http.server 8081
```

---

## YAML Schema Reference

### Top-level keys

```yaml
top_bar:
  title: "MRDTech Homelab"      # Dashboard title
  subtitle: "NOC // ANTON"       # Subtitle text
  show_updated: true             # Show last-updated timestamp
  show_overall_status: true      # Show worst-state badge
  overall_status_logic: worst    # worst | avg | majority
  show_theme_toggle: true        # ◑ button top-right
  logo: ""                       # Path to logo image, or ""

refresh_seconds: 60              # Browser auto-reload interval (seconds)
refresh_minutes: 15              # Generator cron interval (minutes)

output:
  dir: "./output"                # Where to write the HTML file
  file: "index.html"
```

### Theme

```yaml
theme:
  preset: dark-noc               # Built-in theme name (see Themes section)
  auto_switch: true              # Enable day/night auto-switching
  day_theme: light-clean
  night_theme: dark-noc
  day_start: "07:00"
  night_start: "19:00"
  overrides:                     # Override any theme key inline
    accent: "#ff6600"
    font_family: "Inter, sans-serif"
```

### Sections and Cards

```yaml
sections:
  - name: "Infrastructure"
    cards:
      - type: proxmox
        title: "PROXMOX"
        size: normal             # normal | wide | tall | large
        show: [vms, cpu, ram, storage, down_vms]
        thresholds:
          cpu_warn: 75
          cpu_critical: 90
          storage_warn: 80
          storage_critical: 90
        graph: true
        graph_type: sparkline    # sparkline | area | gauge | donut | heatmap
        graph_field: cpu
        graph_hours: 24
        graph_color: "#00ff41"   # optional override
        notes: ""                # optional footnote on card
```

### Card Sizes

| Size     | Grid span  | Description          |
|----------|------------|----------------------|
| `normal` | 1×1        | Default              |
| `wide`   | 2×1        | Two columns wide     |
| `tall`   | 1×2        | Two rows tall        |
| `large`  | 2×2        | 2×2 block            |

Grid is 4 columns desktop → 3 tablet → 2 small → 1 mobile.

---

## Supported Card Types

### Infrastructure

| Type              | Data Source           | Key Fields                          |
|-------------------|-----------------------|-------------------------------------|
| `proxmox`         | Proxmox VE API        | VMs, CPU, RAM, storage, down VMs    |
| `proxmox_storage` | Proxmox VE API        | Storage pools with donut gauges     |
| `docker`          | Portainer API         | Running/total containers, unhealthy |
| `pbs`             | Proxmox Backup Server | Tasks 24h, last backup, datastore   |
| `urbackup`        | URBackup API          | Clients, online status, last backup |
| `home_assistant`  | HA REST API           | Entities, alerts, unavailable       |
| `smart_health`    | Proxmox disk API      | SMART health, disk temps, issues    |

### Monitoring

| Type           | Data Source            | Key Fields                          |
|----------------|------------------------|-------------------------------------|
| `uptime_kuma`  | Kuma /metrics + SQLite | Up/down monitors, cert expiry       |
| `uptime_kuma`  | Portainer exec         | Per-monitor status heatmap          |

### Security

| Type             | Data Source          | Key Fields                             |
|------------------|----------------------|----------------------------------------|
| `wazuh`          | Wazuh API + Indexer  | Agents, alerts 24h, high-severity      |
| `malware_sources`| Wazuh Indexer        | ClamAV, YARA, VirusTotal, Defender 24h |
| `crowdsec`       | CrowdSec LAPI        | Bans, local detections, top scenarios  |
| `cloudflare`     | Cloudflare GraphQL   | Requests, threats, WAF events          |
| `unifi`          | UniFi UDM API        | WAN, clients, devices, IPS, VPN, SSIDs |
| `tailscale`      | Tailscale API v2     | Online devices, exit nodes, key expiry |
| `nginx_proxy`    | NPM API              | Hosts, disabled, cert expiry           |
| `adguard`        | AdGuard API          | Queries, blocked %, latency            |
| `limacharlie`    | LC API               | Sensors, detections 24h                |

### Media

| Type        | Data Source      | Key Fields                         |
|-------------|------------------|------------------------------------|
| `plex`      | Plex API         | Active streams, library counts     |
| `tautulli`  | Tautulli API     | Streams, plays today, top user     |
| `sonarr`    | Sonarr v3 API    | Series, queue, missing             |
| `radarr`    | Radarr v3 API    | Movies, queue, missing             |
| `prowlarr`  | Prowlarr API     | Indexers, healthy/failing          |
| `sabnzbd`   | SABnzbd API      | Status, queue, speed, day total    |
| `overseerr` | Overseerr API    | Pending, approved, available       |

### Storage

| Type     | Data Source      | Key Fields                              |
|----------|------------------|-----------------------------------------|
| `qnap`   | QNAP CGI API     | Volumes, disk health, temps, fans (all 3 units) |

### Custom

| Type         | Config               | Description                         |
|--------------|----------------------|-------------------------------------|
| `custom_url` | url + fields config  | Any REST JSON API with JSONPath      |

#### custom_url example

```yaml
- type: custom_url
  title: "MY SERVICE"
  url: "http://10.10.10.50/api/status"
  headers:
    Authorization: "Bearer mytoken"
  fields:
    - name: "Status"
      path: "$.status"
    - name: "Queue Depth"
      path: "$.queue.length"
  state_field: "Status"
  ok_values: ["ok", "healthy", "up"]
```

---

## Themes

### Built-in Themes

| Name             | Background    | Accent       | Feel                          |
|------------------|---------------|--------------|-------------------------------|
| `dark-noc`       | Black         | Green        | Classic terminal NOC          |
| `light-clean`    | White/grey    | Blue         | Professional / corporate      |
| `midnight-blue`  | Deep navy     | Cyan         | Dark, cool                    |
| `solarized-dark` | Solarized bg  | Teal/green   | Solarized palette             |
| `dracula`        | Dark purple   | Purple/green | Popular dev theme             |
| `nord`           | Muted grey    | Blue/green   | Scandinavian minimal          |

### Inline theme override

Any theme key can be overridden in `dashboard.yaml`:

```yaml
theme:
  preset: dark-noc
  overrides:
    background: "#0d1117"
    card_background: "#161b22"
    card_border: "#30363d"
    accent: "#58a6ff"
    accent_secondary: "#3fb950"
    text_primary: "#e6edf3"
    text_secondary: "#8b949e"
    ok_color: "#3fb950"
    warn_color: "#d29922"
    error_color: "#f85149"
    font_family: "JetBrains Mono, Fira Code, monospace"
```

### Adding a custom theme

Create `themes/my-theme.yaml`:

```yaml
name: my-theme
description: "My custom theme"
background: "#1a1a2e"
card_background: "#16213e"
accent: "#e94560"
# ... all other keys
```

Then in `dashboard.yaml`:

```yaml
theme:
  preset: my-theme
```

---

## Docker Deployment

```bash
# Build and start
docker-compose up -d

# Follow logs
docker-compose logs -f noc-dashboard

# Force regenerate now
docker-compose exec noc-dashboard python3 /app/generator.py

# Stop
docker-compose down
```

### Environment variables (Docker)

| Variable          | Default   | Description                  |
|-------------------|-----------|------------------------------|
| `REFRESH_MINUTES` | `15`      | Generator cron interval      |
| `PORT`            | `8081`    | HTTP server port             |
| `CONFIG_FILE`     | `/app/dashboard.yaml` | Config path     |

---

## Project Structure

```
noc-dashboard/
├── dashboard.yaml          # Your config — edit this
├── generator.py            # Main generator
├── collectors/             # One module per card type
│   ├── proxmox.py
│   ├── wazuh.py
│   ├── docker_portainer.py
│   └── ... (25 total)
├── themes/                 # Theme YAML files
│   ├── dark-noc.yaml
│   ├── light-clean.yaml
│   └── ...
├── state/
│   └── trends.json         # Trend history (gitignored)
├── output/
│   └── index.html          # Generated dashboard
├── screenshots/            # Theme screenshots for README
├── .env.example            # Credential template
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Contributing

1. Fork the repo
2. Add your card type in `collectors/yourservice.py` — implement `collect(E, card_cfg) -> dict`
3. Register it in `generator.py` in `COLLECTOR_MAP` and `CARD_RENDERERS`
4. Add example config to `dashboard.yaml`
5. Submit a PR

### Collector contract

Every `collect()` function:
- Takes `(E: dict, card_cfg: dict | None)` — `E` is the loaded `.env` dict
- Returns a `dict` with at minimum `{"state": "ok|warn|crit|degraded|error"}`
- On failure, returns `{"state": "error", "note": "error message"}` — never raises
- Makes only read-only API calls
- Uses only Python stdlib (no requests, no third-party deps in collectors)

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built for MRDTech homelab. Anton approves.*
