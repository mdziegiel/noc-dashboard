# NOC Dashboard

**An interactive, drag-and-drop React + FastAPI homelab NOC dashboard.**

Deploy it, load your credentials, and get a fully live NOC dashboard — drag cards around, resize them, add or remove card types on the fly, customize every card with a settings panel. Layout persists automatically.

---

![NOC Dashboard — Dark Theme](screenshots/dark-noc.png)

*Dark NOC theme — real MRDTech homelab data*

---

![NOC Dashboard — Light Clean Theme](screenshots/light-clean.png)

*Light Clean theme — same data, professional corporate look*

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Docker Container                   │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │  FastAPI (uvicorn) — server.py               │  │
│  │                                              │  │
│  │  /api/data/{card_type}  ← Python collectors  │  │
│  │  /api/layout            ← layout.json CRUD   │  │
│  │  /api/themes            ← YAML theme loader  │  │
│  │  /api/card-types        ← card registry      │  │
│  │  /api/config            ← dashboard.yaml     │  │
│  │  /                      ← React SPA (static) │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │  React frontend (pre-built, served static)   │  │
│  │  • react-grid-layout (drag + resize)         │  │
│  │  • 27 card types, lazy-loaded chunks         │  │
│  │  • recharts sparklines + area + donuts       │  │
│  │  • 6 themes via CSS variables                │  │
│  └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

One container. One port (8081). No external databases.

---

## Features

- **Interactive drag-and-drop grid** — grab any card by the header, drop it anywhere. Drag edges and corners to resize.
- **27 card types** — Proxmox, Docker/Portainer, PBS, Wazuh SIEM, CrowdSec, UniFi/WAN, Cloudflare, AdGuard, Tailscale, Uptime Kuma, Home Assistant, QNAP, Plex, Tautulli, Sonarr, Radarr, Prowlarr, SABnzbd, Overseerr, Nginx Proxy Manager, URBackup, LimaCharlie, Custom URL, and more.
- **Add Card panel** — click `+` in the top bar to browse all card types with search filter. Click to add.
- **Per-card settings** — click ⚙ on any card to configure: title, refresh interval, graph type, graph color, JSON thresholds, remove.
- **Layout auto-save** — every drag, resize, add, or remove persists to `state/layout.json` within 500ms.
- **6 built-in themes** — `dark-noc`, `light-clean`, `midnight-blue`, `solarized-dark`, `dracula`, `nord`.
- **Auto day/night switching** — swaps theme at configurable hour (default: 07:00 day, 19:00 night).
- **Manual theme toggle** — click the theme button in the top bar to cycle through all themes.
- **Graph support** — sparkline, area, gauge, donut charts. Trend history (48h) stored in `state/trends.json`.
- **Graceful degradation** — one failed collector never kills the page. Cards show error state with message.
- **Docker-ready** — `docker compose up -d`. Done.

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

### 2. Build and run

```bash
docker compose up -d --build
```

Open http://your-host:8081

The React app loads, fetches your layout from `state/layout.json` (bootstrapped from `dashboard.yaml` on first run), and starts polling the collectors.

---

## Configuration

### .env

All service credentials. See `.env.example` for the full list. Every collector reads from this file — nothing is hardcoded.

```env
PROXMOX_HOST=10.10.10.251
PROXMOX_TOKEN_ID=root@pam!hermes
PROXMOX_TOKEN_SECRET=your-token-here
# ... etc
```

### dashboard.yaml

Top-level dashboard config: title, subtitle, theme defaults, auto-switch times, and an initial card layout that bootstraps `layout.json` on first run. After first run, drag-and-drop changes persist to `state/layout.json` directly.

```yaml
top_bar:
  title: "MRDTech NOC"
  subtitle: "Infrastructure Dashboard"

theme:
  preset: dark-noc
  auto_switch: true
  day_theme: light-clean
  night_theme: dark-noc
  day_start: "07:00"
  night_start: "19:00"

refresh_seconds: 60

sections:
  - title: Compute
    cards:
      - type: proxmox
        title: Proxmox
        size: wide   # normal | wide | tall | large
```

### Themes

Edit or add YAML files in `themes/`. Each file maps token names to CSS values. Themes are live-reloaded from the volume mount — no rebuild needed.

```yaml
# themes/my-custom.yaml
background: "#1a1a2e"
accent: "#e94560"
card_background: "#16213e"
# ... any token from THEME_DEFAULTS in server.py
```

---

## Card Types

| Type | Label | Data Source |
|------|-------|-------------|
| `proxmox` | Proxmox | Proxmox API — CPU, RAM, VMs, storage |
| `proxmox_storage` | Proxmox Storage | Proxmox API — storage pool donuts |
| `docker` | Docker | Portainer API — container counts, unhealthy |
| `pbs` | PBS | Proxmox Backup Server API |
| `urbackup` | URBackup | URBackup API |
| `uptime_kuma` | Uptime Kuma | Prometheus metrics |
| `home_assistant` | Home Assistant | HA REST API |
| `smart_health` | Disk Health | Proxmox SMART via API |
| `wazuh` | Wazuh SIEM | Wazuh API — agents, alerts 24h |
| `malware_sources` | Malware Detect | Feed detection counts |
| `crowdsec` | CrowdSec | CrowdSec LAPI |
| `cloudflare` | Cloudflare | CF API — requests, threats, WAF |
| `unifi` | UniFi | UniFi API — WAN, clients, IPS |
| `wan_health` | WAN Health | UniFi API — WAN/internet status |
| `tailscale` | Tailscale | Tailscale API |
| `nginx_proxy` | Nginx Proxy | NPM API — hosts, cert expiry |
| `adguard` | AdGuard Home | AdGuard API — DNS stats |
| `qnap` | NAS Storage | QNAP QTS API |
| `plex` | Plex | Plex API — streams, libraries |
| `tautulli` | Tautulli | Tautulli API |
| `sonarr` | Sonarr | Sonarr v3 API |
| `radarr` | Radarr | Radarr v3 API |
| `prowlarr` | Prowlarr | Prowlarr API |
| `sabnzbd` | SABnzbd | SABnzbd API |
| `overseerr` | Overseerr | Overseerr API |
| `limacharlie` | LimaCharlie | LC REST API |
| `custom_url` | Custom URL | Any JSON endpoint |

---

## API

The FastAPI backend is self-documenting. Swagger UI is at:

```
http://your-host:8081/api/docs
```

Key endpoints:

```
GET  /api/data/{card_type}   Run collector, return live JSON
GET  /api/layout             Current layout config
POST /api/layout             Save layout config
GET  /api/themes             All themes as CSS variable maps
GET  /api/card-types         Registry of all card types
GET  /api/config             Dashboard title/subtitle
GET  /api/health             Health check
```

---

## Development

### Backend only

```bash
pip install -r requirements.txt
cp ~/.hermes/.env .env   # or wherever your creds are
uvicorn server:app --reload --port 8081
```

### Frontend dev server (hot reload)

```bash
cd frontend
npm install
npm run dev   # proxies /api/* to localhost:8081
```

### Full rebuild

```bash
cd frontend && npm run build && cd ..
uvicorn server:app --port 8081
```

---

## Project Structure

```
noc-dashboard/
├── server.py              # FastAPI app — all API routes
├── collectors/            # One .py per data source
│   ├── proxmox.py
│   ├── wazuh.py
│   ├── docker_portainer.py
│   └── ...
├── frontend/
│   ├── src/
│   │   ├── App.jsx        # Root — loads layout, themes, config
│   │   ├── components/
│   │   │   ├── CardGrid.jsx      # react-grid-layout wrapper
│   │   │   ├── CardWrapper.jsx   # Fetcher + header + settings trigger
│   │   │   ├── TopBar.jsx        # Title, theme toggle, Add Card button
│   │   │   ├── AddCardPanel.jsx  # Browse + search all card types
│   │   │   ├── SettingsPanel.jsx # Per-card config drawer
│   │   │   ├── shared.jsx        # MetricRow, Sparkline, DonutGauge, etc.
│   │   │   └── cards/            # One .jsx per card type (lazy-loaded)
│   │   ├── api.js         # fetch helpers
│   │   └── theme.js       # applyTheme, resolveTheme
│   ├── dist/              # Built output (committed)
│   └── package.json
├── themes/                # YAML theme definitions
├── state/
│   ├── layout.json        # Persisted card layout (auto-created)
│   └── trends.json        # Trend history for sparklines
├── dashboard.yaml         # Initial layout + theme config
├── Dockerfile             # Multi-stage: Node build + Python runtime
├── docker-compose.yml
└── .env.example
```

---

## License

MIT
