import React, { useState, useEffect, useRef } from 'react'
import { fetchCardData } from '../api.js'
import SettingsPanel from './SettingsPanel.jsx'

// ── Icon map — lucide SVG paths, rendered inline ───────────────────────────────
// Instead of importing lucide-react bundle, use curated SVG paths to keep bundle lean.
// All icons are 24x24 viewBox, stroke="currentColor" fill="none".
const ICON_PATHS = {
  Server:       'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z',
  HardDrive:    'M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 17.76 4H6.24a2 2 0 0 0-1.79 1.11zM6 16h.01M10 16h.01',
  Box:          'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16zM3.27 6.96 12 12.01l8.73-5.05M12 22.08V12',
  Archive:      'M21 8v13H3V8M1 3h22v5H1zM10 12h4',
  RotateCcw:    'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5',
  Home:         'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10',
  Activity:     'M22 12h-4l-3 9L9 3l-3 9H2',
  Shield:       'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  AlertTriangle:'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01',
  ShieldAlert:  'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM12 8v4M12 16h.01',
  Cloud:        'M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z',
  Eye:          'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  Wifi:         'M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01',
  Network:      'M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 0-2-2V9m0 0h18',
  Globe:        'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z',
  Filter:       'M22 3H2l8 9.46V19l4 2v-8.54L22 3z',
  Database:     'M12 2C6.48 2 2 4.69 2 8s4.48 6 10 6 10-2.69 10-6-4.48-6-10-6zM2 8v4c0 3.31 4.48 6 10 6s10-2.69 10-6V8M2 12v4c0 3.31 4.48 6 10 6s10-2.69 10-6v-4',
  Play:         'M5 3l14 9-14 9V3z',
  BarChart2:    'M18 20V10M12 20V4M6 20v-6',
  Tv:           'M33 7l-5 5-5-5M2 7h20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zM8 21h8M12 17v4',
  Film:         'M19.82 2H4.18A2.18 2.18 0 0 0 2 4.18v15.64A2.18 2.18 0 0 0 4.18 22h15.64A2.18 2.18 0 0 0 22 19.82V4.18A2.18 2.18 0 0 0 19.82 2zM7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5',
  Search:       'M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM21 21l-4.35-4.35',
  Download:     'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  List:         'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  HeartPulse:   'M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7zM3.22 12H9.5l1.5-3 2 4.5 1.5-3H19',
  ExternalLink: 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3',
  GripVertical: 'M9 3h.01M9 8h.01M9 13h.01M9 18h.01M15 3h.01M15 8h.01M15 13h.01M15 18h.01',
  Settings:     'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z',
  X:            'M18 6 6 18M6 6l12 12',
}

function Icon({ name, size = 12, color = 'currentColor', style }) {
  const path = ICON_PATHS[name]
  if (!path) return null
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
    >
      {path.split('M').filter(Boolean).map((segment, i) => (
        <path key={i} d={'M' + segment} />
      ))}
    </svg>
  )
}

// State -> border/dot color
function stateColor(state) {
  switch (state) {
    case 'ok':       return 'var(--ok-color, #00ff41)'
    case 'warn':     return 'var(--warn-color, #ffaa00)'
    case 'crit':
    case 'critical': return 'var(--critical-color, #ff0000)'
    case 'error':    return 'var(--error-color, #ff3333)'
    case 'degraded': return 'var(--text-muted, #555)'
    default:         return 'var(--card-border, #1e1e1e)'
  }
}

function StateDot({ state }) {
  const color = stateColor(state)
  const isCrit = state === 'crit' || state === 'critical' || state === 'error'
  return (
    <span style={{
      display: 'inline-block',
      width: 7,
      height: 7,
      borderRadius: '50%',
      background: color,
      boxShadow: isCrit ? `0 0 5px ${color}` : state === 'ok' ? `0 0 4px ${color}` : 'none',
      flexShrink: 0,
      animation: isCrit ? 'blink 1s infinite' : 'none',
    }} />
  )
}

// Icon for a card type
const TYPE_ICONS = {
  proxmox: 'Server', proxmox_storage: 'HardDrive', docker: 'Box', pbs: 'Archive',
  urbackup: 'RotateCcw', home_assistant: 'Home', smart_health: 'Activity',
  wazuh: 'Shield', malware_sources: 'AlertTriangle', crowdsec: 'ShieldAlert',
  cloudflare: 'Cloud', limacharlie: 'Eye',
  unifi: 'Wifi', wan_health: 'Wifi', tailscale: 'Network', nginx_proxy: 'Globe', adguard: 'Filter',
  qnap: 'Database',
  plex: 'Play', tautulli: 'BarChart2', sonarr: 'Tv', radarr: 'Film',
  prowlarr: 'Search', sabnzbd: 'Download', overseerr: 'List',
  uptime_kuma: 'HeartPulse', custom_url: 'ExternalLink',
}

// Lazy card component map
const CARD_MAP = {
  proxmox:        () => import('./cards/ProxmoxCard.jsx'),
  docker:         () => import('./cards/DockerCard.jsx'),
  pbs:            () => import('./cards/PbsCard.jsx'),
  urbackup:       () => import('./cards/UrbackupCard.jsx'),
  uptime_kuma:    () => import('./cards/UptimeKumaCard.jsx'),
  home_assistant: () => import('./cards/HomeAssistantCard.jsx'),
  smart_health:   () => import('./cards/SmartHealthCard.jsx'),
  wazuh:          () => import('./cards/WazuhCard.jsx'),
  malware_sources:() => import('./cards/MalwareSourcesCard.jsx'),
  crowdsec:       () => import('./cards/CrowdsecCard.jsx'),
  cloudflare:     () => import('./cards/CloudflareCard.jsx'),
  unifi:          () => import('./cards/UnifiCard.jsx'),
  tailscale:      () => import('./cards/TailscaleCard.jsx'),
  nginx_proxy:    () => import('./cards/NginxProxyCard.jsx'),
  adguard:        () => import('./cards/AdguardCard.jsx'),
  qnap:           () => import('./cards/QnapCard.jsx'),
  plex:           () => import('./cards/PlexCard.jsx'),
  tautulli:       () => import('./cards/TautulliCard.jsx'),
  sonarr:         () => import('./cards/SonarrCard.jsx'),
  radarr:         () => import('./cards/RadarrCard.jsx'),
  prowlarr:       () => import('./cards/ProwlarrCard.jsx'),
  sabnzbd:        () => import('./cards/SabnzbdCard.jsx'),
  overseerr:      () => import('./cards/OverseerrCard.jsx'),
  limacharlie:    () => import('./cards/LimaCharlieCard.jsx'),
  custom_url:     () => import('./cards/CustomUrlCard.jsx'),
  wan_health:     () => import('./cards/UnifiCard.jsx'),
  proxmox_storage:() => import('./cards/ProxmoxCard.jsx'),
}

function useCardComponent(type) {
  const [Comp, setComp] = useState(null)
  useEffect(() => {
    const loader = CARD_MAP[type]
    if (loader) {
      loader()
        .then(m => setComp(() => m.default))
        .catch(() => import('./cards/GenericCard.jsx').then(m => setComp(() => m.default)))
    } else {
      import('./cards/GenericCard.jsx').then(m => setComp(() => m.default))
    }
  }, [type])
  return Comp
}

export default function CardWrapper({ card, onUpdate, onRemove, editMode, sseData }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showSettings, setShowSettings] = useState(false)
  const timerRef = useRef(null)
  const CardComp = useCardComponent(card.type)

  const refresh = card.config?.refresh_seconds || 60

  function doFetch() {
    fetchCardData(card.type)
      .then(d => { setData(d); setError(null); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }

  useEffect(() => {
    doFetch()
    timerRef.current = setInterval(doFetch, refresh * 1000)
    return () => clearInterval(timerRef.current)
  }, [card.type, refresh])

  // If SSE pushed fresh data, apply it without full refetch
  useEffect(() => {
    if (sseData && sseData._ts) {
      const current_ts = data?._ts || 0
      if (sseData._ts > current_ts) {
        setData(sseData)
        setError(null)
        setLoading(false)
      }
    }
  }, [sseData])

  const state = data?.state || (error ? 'error' : null)
  const trends = data?._trends || null
  const borderColor = stateColor(state)
  const iconName = card.config?.icon || TYPE_ICONS[card.type] || 'Activity'

  function handleSave(updates) {
    onUpdate(card.id, updates)
    setTimeout(doFetch, 100)
  }

  return (
    <div
      className="noc-card"
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--card-background, #111)',
        borderRadius: 'var(--card-border-radius, 4px)',
        boxShadow: 'var(--card-shadow, 0 0 8px rgba(0,255,65,0.08))',
        overflow: 'hidden',
        position: 'relative',
        borderLeft: `3px solid ${borderColor}`,
        transition: 'border-color 0.3s, box-shadow 0.2s',
      }}
    >
      {/* Card header — drag handle in edit mode */}
      <div
        className={editMode ? 'card-drag-handle' : ''}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '5px 10px',
          borderBottom: '1px solid var(--card-border, #1e1e1e)',
          minHeight: 28,
          flexShrink: 0,
          cursor: editMode ? 'grab' : 'default',
          background: editMode ? 'rgba(0,255,65,0.03)' : 'transparent',
          userSelect: editMode ? 'none' : 'auto',
        }}
      >
        {/* Drag icon in edit mode */}
        {editMode && (
          <span style={{ color: 'var(--accent, #00ff41)', opacity: 0.5, flexShrink: 0, display: 'flex', alignItems: 'center' }}>
            <Icon name="GripVertical" size={11} />
          </span>
        )}

        {/* Card type icon */}
        <span style={{ color: borderColor, flexShrink: 0, display: 'flex', alignItems: 'center', opacity: 0.8 }}>
          <Icon name={iconName} size={11} color={borderColor} />
        </span>

        <StateDot state={state} />

        <span style={{
          flex: 1,
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: '0.12em',
          color: 'var(--text-secondary, #a0a0a0)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}>
          {card.title || card.type}
        </span>

        {/* Gear (always visible) */}
        <button
          onClick={() => setShowSettings(true)}
          title="Card settings"
          style={{
            background: 'none',
            border: 'none',
            color: editMode ? 'var(--accent, #00ff41)' : 'var(--text-muted, #555)',
            cursor: 'pointer',
            fontSize: 11,
            lineHeight: 1,
            padding: '0 2px',
            fontFamily: 'inherit',
            flexShrink: 0,
            opacity: editMode ? 1 : 0.6,
            display: 'flex',
            alignItems: 'center',
            transition: 'color 0.15s, opacity 0.15s',
          }}
        >
          <Icon name="Settings" size={11} color={editMode ? 'var(--accent, #00ff41)' : 'var(--text-muted, #555)'} />
        </button>

        {/* X remove button — only in edit mode */}
        {editMode && (
          <button
            onClick={() => onRemove(card.id)}
            title="Remove card"
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--error-color, #ff3333)',
              cursor: 'pointer',
              fontSize: 11,
              lineHeight: 1,
              padding: '0 2px',
              fontFamily: 'inherit',
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <Icon name="X" size={11} color="var(--error-color, #ff3333)" />
          </button>
        )}
      </div>

      {/* Card body */}
      <div style={{
        flex: 1,
        padding: '8px 10px',
        overflowY: 'auto',
        overflowX: 'hidden',
      }}>
        {loading && (
          <>
            <div className="skeleton" style={{ height: 12, marginBottom: 6, borderRadius: 2 }} />
            <div className="skeleton" style={{ height: 12, marginBottom: 6, width: '70%', borderRadius: 2 }} />
            <div className="skeleton" style={{ height: 12, marginBottom: 6, width: '85%', borderRadius: 2 }} />
          </>
        )}
        {!loading && error && (
          <div style={{ fontSize: 11, color: 'var(--error-color, #ff3333)', padding: '4px 0' }}>
            ⚠ {error}
          </div>
        )}
        {!loading && !error && data && CardComp && (
          <CardComp data={data} config={card.config || {}} trends={trends} />
        )}
        {!loading && !error && data && !CardComp && (
          <div style={{ fontSize: 11, color: 'var(--text-muted, #555)' }}>Loading...</div>
        )}
      </div>

      {/* Settings panel */}
      {showSettings && (
        <SettingsPanel
          card={card}
          onSave={handleSave}
          onRemove={onRemove}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  )
}
