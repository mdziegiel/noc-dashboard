import React, { useState, useEffect, useRef } from 'react'
import { fetchCardData } from '../api.js'

// Lazy card component map — each card renders card-b and sub content
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

// Normalize state string to the CSS class suffix the reference uses
function normalizeState(state) {
  if (!state) return 'degraded'
  if (state === 'critical') return 'crit'
  if (state === 'error') return 'crit'
  return state  // ok, warn, crit, degraded
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
      .then(d => {
        setData(d)
        setError(null)
        setLoading(false)
        if (onData) onData(card.type, d)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
        if (onData) onData(card.type, { state: 'error', note: e.message })
      })
  }

  useEffect(() => {
    doFetch()
    timerRef.current = setInterval(doFetch, refresh * 1000)
    return () => clearInterval(timerRef.current)
  }, [card.type, refresh])

  const state = normalizeState(data?.state || (error ? 'error' : 'degraded'))
  const trends = data?._trends || null

  // Handle card click — open modal (matches reference focusCard behavior)
  function handleClick(e) {
    if (editMode) return
    const modal = document.getElementById('card-modal')
    const titleEl = document.getElementById('card-modal-title')
    const bodyEl = document.getElementById('card-modal-body')
    if (modal && titleEl && bodyEl) {
      titleEl.textContent = card.title || card.type
      // Build a simple text representation of card data
      bodyEl.innerHTML = data
        ? Object.entries(data)
            .filter(([k]) => !k.startsWith('_') && k !== 'state')
            .map(([k, v]) => `<div><b>${k}</b>: ${typeof v === 'object' ? JSON.stringify(v) : v}</div>`)
            .join('')
        : '<div>No data</div>'
      modal.style.display = 'block'
    }
  }

  return (
    <div
      className={`card s-${state}`}
      data-title={card.title || card.type}
      data-state={state}
      onClick={handleClick}
      style={{ height: '100%', cursor: editMode ? 'default' : 'pointer', boxSizing: 'border-box', overflow: 'hidden' }}
    >
      {/* Card header — drag handle in edit mode */}
      <div
        className={`card-h${editMode ? ' card-drag-handle' : ''}`}
        onClick={e => e.stopPropagation()}
      >
        <span className="dot" />
        <h3 style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {card.title || card.type}
        </h3>
        {/* Gear icon — always visible */}
        <button
          title="Card settings"
          onClick={e => { e.stopPropagation(); onOpenSettings && onOpenSettings(card) }}
          style={{
            background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer',
            fontSize: 13, padding: '0 4px', lineHeight: 1, fontFamily: 'inherit',
            opacity: editMode ? 1 : 0.5,
          }}
        >⚙</button>
        {editMode && (
          <button
            title="Remove card"
            onClick={e => { e.stopPropagation(); onRemove && onRemove(card.id) }}
            style={{
              background: 'none', border: 'none', color: 'var(--crit)', cursor: 'pointer',
              fontSize: 13, padding: '0 4px', lineHeight: 1, fontFamily: 'inherit',
            }}
          >✕</button>
        )}
      </div>

      {/* Card body */}
      <div className="card-b">
        {loading && (
          <div className="metric">
            <div className="m-v" style={{ color: 'var(--muted)' }}>…</div>
            <div className="m-l">loading</div>
          </div>
        )}
        {!loading && error && (
          <div className="metric m-crit">
            <div className="m-v">ERR</div>
            <div className="m-l" style={{ fontSize: 10, wordBreak: 'break-all' }}>{error.slice(0, 60)}</div>
          </div>
        )}
        {!loading && !error && data && CardComp && (
          <CardComp data={data} config={card.config || {}} trends={trends} />
        )}
      </div>
    </div>
  )
}
