import React, { useState, useEffect, useRef } from 'react'
import { fetchCardData } from '../api.js'
import SettingsPanel from './SettingsPanel.jsx'

// Map state to border color CSS variable
function stateColor(state) {
  switch (state) {
    case 'ok': return 'var(--ok-color, #00ff41)'
    case 'warn': return 'var(--warn-color, #ffaa00)'
    case 'crit':
    case 'critical': return 'var(--critical-color, #ff0000)'
    case 'error': return 'var(--error-color, #ff3333)'
    case 'degraded': return 'var(--text-muted, #555)'
    default: return 'var(--card-border, #1e1e1e)'
  }
}

function StateDot({ state }) {
  const color = stateColor(state)
  const isCrit = state === 'crit' || state === 'critical'
  return (
    <span
      style={{
        display: 'inline-block',
        width: 7,
        height: 7,
        borderRadius: '50%',
        background: color,
        flexShrink: 0,
        animation: isCrit ? 'blink 1s infinite' : 'none',
      }}
    />
  )
}

const styles = {
  wrapper: {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    background: 'var(--card-background, #111)',
    borderRadius: 'var(--card-border-radius, 4px)',
    boxShadow: 'var(--card-shadow, 0 0 8px rgba(0,255,65,0.08))',
    overflow: 'hidden',
    position: 'relative',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '5px 10px',
    borderBottom: '1px solid var(--card-border, #1e1e1e)',
    minHeight: 28,
    flexShrink: 0,
  },
  headerTitle: {
    flex: 1,
    fontSize: '10px',
    textTransform: 'uppercase',
    letterSpacing: '0.12em',
    color: 'var(--text-secondary, #a0a0a0)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  gearBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted, #555)',
    cursor: 'pointer',
    fontSize: '13px',
    lineHeight: 1,
    padding: '0 2px',
    fontFamily: 'inherit',
    flexShrink: 0,
  },
  body: {
    flex: 1,
    padding: '8px 10px',
    overflowY: 'auto',
    overflowX: 'hidden',
  },
  skeleton: {
    height: 12,
    marginBottom: 6,
    borderRadius: 2,
  },
  errorMsg: {
    fontSize: 11,
    color: 'var(--error-color, #ff3333)',
    padding: '4px 0',
  },
}

// Lazy card component map
const CARD_MAP = {
  proxmox: () => import('./cards/ProxmoxCard.jsx'),
  docker: () => import('./cards/DockerCard.jsx'),
  pbs: () => import('./cards/PbsCard.jsx'),
  urbackup: () => import('./cards/UrbackupCard.jsx'),
  uptime_kuma: () => import('./cards/UptimeKumaCard.jsx'),
  home_assistant: () => import('./cards/HomeAssistantCard.jsx'),
  smart_health: () => import('./cards/SmartHealthCard.jsx'),
  wazuh: () => import('./cards/WazuhCard.jsx'),
  malware_sources: () => import('./cards/MalwareSourcesCard.jsx'),
  crowdsec: () => import('./cards/CrowdsecCard.jsx'),
  cloudflare: () => import('./cards/CloudflareCard.jsx'),
  unifi: () => import('./cards/UnifiCard.jsx'),
  tailscale: () => import('./cards/TailscaleCard.jsx'),
  nginx_proxy: () => import('./cards/NginxProxyCard.jsx'),
  adguard: () => import('./cards/AdguardCard.jsx'),
  qnap: () => import('./cards/QnapCard.jsx'),
  plex: () => import('./cards/PlexCard.jsx'),
  tautulli: () => import('./cards/TautulliCard.jsx'),
  sonarr: () => import('./cards/SonarrCard.jsx'),
  radarr: () => import('./cards/RadarrCard.jsx'),
  prowlarr: () => import('./cards/ProwlarrCard.jsx'),
  sabnzbd: () => import('./cards/SabnzbdCard.jsx'),
  overseerr: () => import('./cards/OverseerrCard.jsx'),
  limacharlie: () => import('./cards/LimaCharlieCard.jsx'),
  custom_url: () => import('./cards/CustomUrlCard.jsx'),
  wan_health: () => import('./cards/UnifiCard.jsx'),
  proxmox_storage: () => import('./cards/ProxmoxCard.jsx'),
}

function useCardComponent(type) {
  const [Comp, setComp] = useState(null)
  useEffect(() => {
    const loader = CARD_MAP[type]
    if (loader) {
      loader().then(m => setComp(() => m.default)).catch(() => {
        import('./cards/GenericCard.jsx').then(m => setComp(() => m.default))
      })
    } else {
      import('./cards/GenericCard.jsx').then(m => setComp(() => m.default))
    }
  }, [type])
  return Comp
}

export default function CardWrapper({ card, onUpdate, onRemove }) {
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

  const state = data?.state || (error ? 'error' : null)
  const trends = data?._trends || null

  const borderColor = stateColor(state)

  function handleSave(updates) {
    onUpdate(card.id, updates)
    // Re-fetch with new config
    setTimeout(doFetch, 100)
  }

  return (
    <div
      style={{
        ...styles.wrapper,
        borderLeft: `3px solid ${borderColor}`,
      }}
    >
      <div style={styles.header}>
        <StateDot state={state} />
        <span style={styles.headerTitle}>{card.title || card.type}</span>
        <button style={styles.gearBtn} onClick={() => setShowSettings(true)}>⚙</button>
      </div>
      <div style={styles.body}>
        {loading && (
          <>
            <div className="skeleton" style={styles.skeleton} />
            <div className="skeleton" style={{ ...styles.skeleton, width: '70%' }} />
            <div className="skeleton" style={{ ...styles.skeleton, width: '85%' }} />
          </>
        )}
        {!loading && error && (
          <div style={styles.errorMsg}>⚠ {error}</div>
        )}
        {!loading && !error && data && CardComp && (
          <CardComp data={data} config={card.config || {}} trends={trends} />
        )}
        {!loading && !error && data && !CardComp && (
          <div style={{ fontSize: 11, color: 'var(--text-muted, #555)' }}>Loading...</div>
        )}
      </div>
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
