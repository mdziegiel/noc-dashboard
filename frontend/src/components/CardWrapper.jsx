import React, { useState, useEffect, useRef } from 'react'
import { fetchCardData } from '../api.js'

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
  wan_health:     () => import('./cards/UnifiCard.jsx').then(m => ({ default: m.WanHealthCard })),
  tailscale:      () => import('./cards/TailscaleCard.jsx'),
  nginx_proxy:    () => import('./cards/NginxProxyCard.jsx'),
  adguard:        () => import('./cards/AdguardCard.jsx'),
  qnap:           () => import('./cards/QnapCard.jsx'),
  proxmox_storage:() => import('./cards/ProxmoxStorageCard.jsx'),
  plex:           () => import('./cards/PlexCard.jsx'),
  tautulli:       () => import('./cards/TautulliCard.jsx'),
  sonarr:         () => import('./cards/SonarrCard.jsx'),
  radarr:         () => import('./cards/RadarrCard.jsx'),
  prowlarr:       () => import('./cards/ProwlarrCard.jsx'),
  sabnzbd:        () => import('./cards/SabnzbdCard.jsx'),
  overseerr:      () => import('./cards/OverseerrCard.jsx'),
  limacharlie:    () => import('./cards/LimaCharlieCard.jsx'),
  custom_url:     () => import('./cards/CustomUrlCard.jsx'),
}

function useCardComponent(type) {
  const [Comp, setComp] = useState(null)
  useEffect(() => {
    const loader = CARD_MAP[type]
    if (loader) {
      loader().then(m => setComp(() => m.default)).catch(() => import('./cards/GenericCard.jsx').then(m => setComp(() => m.default)))
    } else {
      import('./cards/GenericCard.jsx').then(m => setComp(() => m.default))
    }
  }, [type])
  return Comp
}

function normalizeState(state) {
  if (!state) return 'degraded'
  if (state === 'critical' || state === 'error') return 'crit'
  return state
}

export default function CardWrapper({ card, onUpdate, onRemove, onOpenSettings, onData, editMode }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)
  const CardComp = useCardComponent(card.type)
  const refresh = card.config?.refresh_seconds || 60

  function doFetch() {
    fetchCardData(card.type)
      .then(d => { setData(d); setError(null); setLoading(false); if (onData) onData(card.type, d) })
      .catch(e => { setError(e.message); setLoading(false); if (onData) onData(card.type, { state: 'error', note: e.message }) })
  }

  useEffect(() => {
    doFetch()
    timerRef.current = setInterval(doFetch, refresh * 1000)
    return () => clearInterval(timerRef.current)
  }, [card.type, refresh])

  const state = normalizeState(data?.state || (error ? 'error' : 'degraded'))
  const title = card.title || card.type.toUpperCase().replace(/_/g,' ')

  // Open card modal on click (matches focusCard behavior from 9969)
  function handleCardClick(e) {
    if (editMode) return
    const modal = document.getElementById('card-modal')
    if (!modal) return
    document.getElementById('card-modal-title').textContent = title
    const bodyEl = document.getElementById('card-modal-body')
    if (data) {
      bodyEl.innerHTML = Object.entries(data)
        .filter(([k]) => !k.startsWith('_') && k !== 'state')
        .map(([k, v]) => `<div><b>${k.replace(/_/g,' ')}</b>: ${typeof v === 'object' ? JSON.stringify(v) : v}</div>`)
        .join('')
    }
    modal.style.display = 'flex'
    document.body.style.overflow = 'hidden'
  }

  return (
    <div
      className={`card s-${state}`}
      data-title={title}
      data-state={state}
      onClick={handleCardClick}
      style={{ cursor: editMode ? 'grab' : 'pointer', position: 'relative' }}
    >
      {/* Edit mode overlay buttons */}
      {editMode && (
        <div className="noc-card-edit-overlay" onClick={e => e.stopPropagation()}>
          {onOpenSettings && (
            <button className="noc-card-edit-btn" onClick={() => onOpenSettings(card)} title="Card settings">⚙</button>
          )}
          {onRemove && (
            <button className="noc-card-edit-btn remove" onClick={() => onRemove(card.id)} title="Remove">✕</button>
          )}
        </div>
      )}
      {/* Header — exact generator structure */}
      <div className="card-h">
        <span className="dot" />
        <h3>{title}</h3>
      </div>
      {/* Body */}
      {loading ? (
        <div className="card-b">
          <div className="metric"><div className="m-v" style={{ color:'var(--muted)' }}>…</div><div className="m-l">loading</div></div>
        </div>
      ) : error ? (
        <>
          <div className="card-b"><div className="metric m-crit"><div className="m-v">ERR</div><div className="m-l">{error.slice(0,40)}</div></div></div>
        </>
      ) : data && CardComp ? (
        <CardComp data={data} config={card.config || {}} />
      ) : (
        <div className="card-b"><div className="metric"><div className="m-v">…</div><div className="m-l">loading</div></div></div>
      )}
    </div>
  )
}
