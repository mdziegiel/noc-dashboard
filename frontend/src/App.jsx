import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fetchLayout, fetchConfig, saveLayout, fetchFirstLaunch, fetchAuthStatus, logout } from './api.js'
import CardWrapper from './components/CardWrapper.jsx'
import AddCardPanel from './components/AddCardPanel.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import IntegrationsPage from './components/IntegrationsPage.jsx'
import { HealthDetailModal, IntelligencePanel, useIntelligence } from './components/IntelligencePanel.jsx'

function isGenuineBackdropClick(e, panelSelector) {
  if (!e || e.target !== e.currentTarget) return false
  const doc = document.documentElement
  if (typeof e.clientX === 'number' && (e.clientX >= doc.clientWidth || e.clientY >= doc.clientHeight)) return false
  const panel = panelSelector ? document.querySelector(panelSelector) : null
  const path = typeof e.composedPath === 'function' ? e.composedPath() : []
  if (panel && (panel.contains(e.target) || path.includes(panel))) return false
  return true
}

// Default sections — mirrors NOC 1 / generate_dashboard.py. Used as fallback
// when layout.json has no sections array (old layouts get migrated by server, but
// we keep this for the rare case where the client sees an unmigrated layout).
const DEFAULT_SECTIONS_DEF = [
  { id: 'system_status',    label: 'System Status',               collapsed: false },
  { id: 'security_network', label: 'Security & Network',          collapsed: false },
  { id: 'media_downloads',  label: 'Media & Downloads',           collapsed: false },
  { id: 'qnap_storage',     label: 'QNAP Storage Appliances',     collapsed: false },
  { id: 'proxmox_storage',  label: 'Proxmox Storage Utilization', collapsed: false, panelbox: true },
  { id: 'uptime_history',   label: 'Uptime History (last 24h)',   collapsed: false, panelbox: true, historyPanel: true },
  { id: 'certs_alerts',     label: 'Certificates & Active Alerts', collapsed: false, twocol: true, certsPanel: true },
]

// Legacy type→section mapping for layouts that still have no card.section field
const TYPE_TO_SECTION = {
  wan_health: 'system_status', wan_health_sec: 'security_network',
  proxmox: 'system_status', home_assistant: 'system_status',
  uptime_kuma: 'system_status', docker: 'system_status',
  pbs: 'system_status', urbackup: 'system_status', smart_health: 'system_status',
  unifi: 'security_network', nginx_proxy: 'security_network',
  cloudflare: 'security_network', wazuh: 'security_network',
  crowdsec: 'security_network', limacharlie: 'security_network',
  adguard: 'security_network', adguard2: 'security_network',
  tailscale: 'security_network', malware_sources: 'security_network',
  plex: 'media_downloads', tautulli: 'media_downloads',
  sonarr: 'media_downloads', radarr: 'media_downloads',
  sabnzbd: 'media_downloads', overseerr: 'media_downloads', prowlarr: 'media_downloads',
  qnap: 'qnap_storage',
  proxmox_storage: 'proxmox_storage',
  uptime_kuma_detail: 'uptime_history',
  custom_url: 'certs_alerts',
}

function cardSectionId(card) {
  return card.section || TYPE_TO_SECTION[card.type] || 'system_status'
}

function isStandaloneHealthCard(card) {
  const type = String(card?.type || '').toLowerCase().replace(/[- ]/g, '_')
  const title = String(card?.title || '').toLowerCase()
  return ['noc_health_score', 'health_score', 'noc_health', 'health'].includes(type)
    || title.includes('noc health score')
}

function formatDate(d) {
  if (!d) return '—'
  return d.toLocaleDateString('en-US', { weekday:'short', month:'short', day:'numeric', year:'numeric', timeZone:'America/New_York' })
    + ' ' + d.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', timeZoneName:'short', timeZone:'America/New_York' })
}

function updateFavicon(health) {
  const color = health === 'crit' ? '#ff3b3b' : health === 'warn' ? '#ffcc00' : health === 'ok' ? '#00ff41' : '#555555'
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="${color}"/></svg>`
  let el = document.getElementById('noc-favicon')
  if (!el) {
    el = document.createElement('link')
    el.id = 'noc-favicon'
    el.rel = 'icon'
    el.type = 'image/svg+xml'
    document.head.appendChild(el)
  }
  el.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}

// Proxmox Storage panelbox — renders gauges exactly like 9969's panelbox section
function ProxmoxStoragePanel({ data }) {
  if (!data) return <div className="panelbox"><div className="empty">Loading storage data…</div></div>
  const storages = data.storage || []
  if (storages.length === 0) return <div className="panelbox"><div className="empty">No storage data</div></div>
  const circ = 2 * Math.PI * 52
  return (
    <div className="panelbox">
      <div className="gauges">
        {storages.map((s, i) => {
          const pct = Math.round(s.pct ?? s.used_pct ?? 0)
          const state = pct >= 90 ? 'crit' : pct >= 80 ? 'warn' : 'ok'
          const dash = ((pct / 100) * circ).toFixed(1)
          return (
            <div key={i} className="gauge">
              <svg viewBox="0 0 140 140" className={`g-${state}`}>
                <circle cx="70" cy="70" r="52" className="g-track"/>
                <circle cx="70" cy="70" r="52" className="g-val"
                  strokeDasharray={`${dash} ${circ.toFixed(1)}`}
                  transform="rotate(-90 70 70)"/>
                <text x="70" y="64" className="g-pct">{pct}%</text>
                <text x="70" y="86" className="g-lbl">{s.name}</text>
              </svg>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Uptime History panel — hbar rows matching 9969's panelbox with hbar-row structure
function UptimeHistoryPanel({ data }) {
  const monitors = data?.history_monitors || data?.monitors || []
  if (monitors.length === 0) {
    return (
      <div className="panelbox">
        <div className="hbar-head">
          <span className="hbar-name"></span>
          <span className="hbar-legend">
            -24h → now &nbsp;
            <span className="hbar b-up" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px 0 8px'}}></span>up&nbsp;
            <span className="hbar b-down" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px'}}></span>down&nbsp;
            <span className="hbar b-other" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px'}}></span>other&nbsp;
            <span className="hbar b-none" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px'}}></span>no data
          </span>
        </div>
        <div className="empty">Uptime Kuma history loading…</div>
      </div>
    )
  }
  return (
    <div className="panelbox">
      <div className="hbar-head">
        <span className="hbar-name"></span>
        <span className="hbar-legend">
          -24h → now &nbsp;
          <span className="hbar b-up" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px 0 8px'}}></span>up&nbsp;
          <span className="hbar b-down" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px'}}></span>down&nbsp;
          <span className="hbar b-other" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px'}}></span>other&nbsp;
          <span className="hbar b-none" style={{display:'inline-block',width:13,height:13,borderRadius:2,verticalAlign:'middle',margin:'0 2px'}}></span>no data
        </span>
      </div>
      {monitors.map((m, i) => {
        const cells = m.cells || []
        return (
          <div key={i} className="hbar-row">
            <span className="hbar-name">{m.name}</span>
            <span className="hbar-cells">
              {cells.map((c, j) => {
                const cls = c === 1 ? 'b-up' : c === 0 ? 'b-down' : c === 2 ? 'b-other' : 'b-none'
                return <span key={j} className={`hbar ${cls}`}></span>
              })}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// Certs & Alerts twocol panel — exact 9969 structure
function CertsAlertsPanel({ nginxData, uptimeData, alertItems }) {
  const allCerts = []
  if (nginxData?.cert_list) {
    for (const c of nginxData.cert_list) allCerts.push(c)
  } else if (nginxData?.certs && Array.isArray(nginxData.certs)) {
    for (const c of nginxData.certs) allCerts.push(c)
  }
  if (uptimeData?.certs && Array.isArray(uptimeData.certs)) {
    for (const c of uptimeData.certs) allCerts.push(c)
  }

  return (
    <div className="twocol">
      <div className="panelbox">
        <h4>TLS CERT EXPIRY</h4>
        {allCerts.length === 0 ? (
          <div className="empty">No cert data</div>
        ) : (
          <div className="certs">
            {allCerts.map((c, i) => {
              const days = c.days ?? c.days_remaining ?? null
              const valid = c.valid !== false && c.is_valid !== false
              const cls = !valid ? 'c-crit' : days != null && days <= 14 ? 'c-crit' : days != null && days <= 30 ? 'c-warn' : 'c-ok'
              const label = !valid ? 'INVALID' : days != null ? `${days}d` : '?'
              const name = c.name || c.domain || c.host || '—'
              return (
                <div key={i} className={`cert ${cls}`}>
                  <div className="cert-d">{label}</div>
                  <div className="cert-n">{name}</div>
                </div>
              )
            })}
          </div>
        )}
      </div>
      <div className="panelbox">
        <h4>ACTIVE ALERTS</h4>
        {alertItems.length === 0 ? (
          <div className="empty ok-empty">All clear — no active alerts</div>
        ) : (
          <ul className="alerts">
            {alertItems.map((item, i) => (
              <li key={i}>{item.text}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── Section header component ─────────────────────────────────────────────────
// In view mode: plain label with collapse toggle.
// In edit mode: inline rename, drag handle, delete button.
function SectionHeader({ section, editMode, onRename, onDelete, onToggleCollapse, dragHandleRef }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(section.label)
  const inputRef = useRef(null)

  useEffect(() => { setDraft(section.label) }, [section.label])
  useEffect(() => { if (editing && inputRef.current) inputRef.current.focus() }, [editing])

  function commitRename() {
    setEditing(false)
    const trimmed = draft.trim()
    if (trimmed && trimmed !== section.label) onRename(section.id, trimmed)
    else setDraft(section.label)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') commitRename()
    if (e.key === 'Escape') { setEditing(false); setDraft(section.label) }
  }

  return (
    <div
      className={`section-label section-label-row${editMode ? ' section-label-edit' : ''}`}
      style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: editMode ? 'default' : 'pointer' }}
    >
      {/* Collapse toggle — always visible */}
      <button
        className="section-collapse-btn"
        onClick={() => !editMode && onToggleCollapse(section.id)}
        title={section.collapsed ? 'Expand section' : 'Collapse section'}
        style={{
          background: 'none', border: 'none', color: 'var(--green-dim)',
          cursor: 'pointer', padding: '0 2px', fontSize: 11, lineHeight: 1,
          opacity: editMode ? 0.4 : 1,
          flexShrink: 0,
        }}
      >
        {section.collapsed ? '▶' : '▼'}
      </button>

      {editMode && (
        /* Drag handle — only in edit mode; SortableJS uses data-section-drag attr */
        <span
          ref={dragHandleRef}
          className="section-drag-handle"
          title="Drag to reorder section"
          style={{
            cursor: 'grab', color: 'var(--muted)', fontSize: 13,
            flexShrink: 0, userSelect: 'none', lineHeight: 1,
          }}
        >⠿</span>
      )}

      {editMode && editing ? (
        <input
          ref={inputRef}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commitRename}
          onKeyDown={handleKeyDown}
          className="section-rename-input"
          style={{
            background: 'transparent', border: 'none',
            borderBottom: '1px solid var(--green)', outline: 'none',
            color: 'var(--green-dim)', fontSize: 11, letterSpacing: '3px',
            textTransform: 'uppercase', fontFamily: 'inherit', fontWeight: 600,
            padding: '0 2px', flex: 1, minWidth: 80,
          }}
          maxLength={60}
        />
      ) : (
        <span
          style={{ flex: 1, textTransform: 'uppercase', letterSpacing: '3px', fontSize: 11 }}
          onClick={() => editMode && setEditing(true)}
          title={editMode ? 'Click to rename' : undefined}
        >
          {section.label}
          {editMode && (
            <span style={{ marginLeft: 6, color: 'var(--muted)', fontSize: 10, fontStyle: 'italic', letterSpacing: '1px', textTransform: 'none' }}>
              (click to rename)
            </span>
          )}
        </span>
      )}

      {editMode && (
        <button
          onClick={() => onDelete(section.id)}
          title="Delete section"
          style={{
            background: 'none', border: '1px solid var(--crit)', color: 'var(--crit)',
            borderRadius: 3, cursor: 'pointer', fontSize: 10, padding: '1px 6px',
            lineHeight: 1.4, flexShrink: 0,
          }}
        >✕ DELETE</button>
      )}
    </div>
  )
}

export default function App() {
  const [layout, setLayout] = useState(null)
  const [config, setConfig] = useState({})
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showIntegrations, setShowIntegrations] = useState(false)
  const [showIntel, setShowIntel] = useState(false)
  const [showHealthDetail, setShowHealthDetail] = useState(false)
  const [firstLaunch, setFirstLaunch] = useState(false)
  const [cardData, setCardData] = useState({})
  const [settingsCard, setSettingsCard] = useState(null)
  const [overallHealth, setOverallHealth] = useState('ok')
  const [authUser, setAuthUser] = useState({ username: 'admin', role: 'Administrator' })
  const [showAlerts, setShowAlerts] = useState(false)
  const gearMenuRef = useRef(null)
  const [gearMenuOpen, setGearMenuOpen] = useState(false)
  const intelligence = useIntelligence()
  // addCardTargetSection: when clicking "+ ADD" on a specific section
  const [addCardTargetSection, setAddCardTargetSection] = useState(null)
  const saveTimerRef = useRef(null)
  const layoutRef = useRef(null)
  const editSnapshotRef = useRef(null)
  const editModeRef = useRef(false)
  const sortablesRef = useRef([])          // card sortables
  const sectionSortableRef = useRef(null)  // section sortable

  useEffect(() => {
    Promise.all([fetchLayout(), fetchConfig(), fetchFirstLaunch()])
      .then(([lay, cfg, fl]) => {
        setLayout(lay); setConfig(cfg)
        setLastUpdated(new Date())
        layoutRef.current = lay
        applyThemeAttr('dark-noc')
        setLoading(false)
        if (fl?.first_launch) setFirstLaunch(true)
      })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchAuthStatus()
      .then(st => {
        if (st?.username) setAuthUser({ username: st.username, role: st.role || 'Administrator' })
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    function onDocClick(e) {
      const path = typeof e.composedPath === 'function' ? e.composedPath() : []
      const menu = gearMenuRef.current
      if (menu && !menu.contains(e.target) && !path.includes(menu)) setGearMenuOpen(false)
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [])

  async function handleLogout() {
    try { await logout() } catch {}
    window.location.reload()
  }

  function applyThemeAttr(name) {
    const themeMap = { 'dark-noc': '', 'light-clean': 'light', 'midnight-blue': 'midnight', 'solarized-dark': 'solarized', 'dracula': 'dracula', 'nord': 'nord', 'gruvbox': 'gruvbox', 'tokyo': 'tokyo' }
    const attr = themeMap[name] ?? ''
    if (attr) { document.documentElement.setAttribute('data-theme', attr); document.body.setAttribute('data-theme', attr) }
    else { document.documentElement.removeAttribute('data-theme'); document.body.removeAttribute('data-theme') }
  }

  function cycleTheme() {
    const names = ['dark-noc','light-clean','midnight-blue','solarized-dark','dracula','nord','gruvbox','tokyo']
    const cur = layoutRef.current?.theme || 'dark-noc'
    const next = names[(names.indexOf(cur) + 1) % names.length]
    const newLayout = { ...layoutRef.current, theme: next }
    setLayout(newLayout); layoutRef.current = newLayout
    applyThemeAttr(next)
    debouncedSave(newLayout)
  }

  useEffect(() => {
    let worst = 'ok'
    for (const v of Object.values(cardData)) {
      const st = v?.state
      if (st === 'crit' || st === 'critical' || st === 'error') { worst = 'crit'; break }
      if (st === 'warn' && worst !== 'crit') worst = 'warn'
    }
    setOverallHealth(worst)
    updateFavicon(worst)
  }, [cardData])

  const handleCardData = useCallback((cardType, data) => {
    let nextData = data
    if (cardType === 'proxmox' && data && data.state !== 'error') {
      const downVms = Array.isArray(data.down_vms) ? data.down_vms : []
      const running = Number(data.vms_running ?? -1)
      const total = Number(data.vms_total ?? -2)
      if (downVms.length === 0 && total >= 0 && running === total) {
        nextData = { ...data, state: 'ok' }
      }
    }
    setCardData(prev => ({ ...prev, [cardType]: nextData }))
  }, [])

  useEffect(() => {
    editModeRef.current = editMode
  }, [editMode])

  const debouncedSave = useCallback((newLayout) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    if (editModeRef.current) return
    saveTimerRef.current = setTimeout(() => {
      saveLayout(newLayout).catch(() => {})
    }, 500)
  }, [])

  const handleUpdateCard = useCallback((cardId, updates) => {
    const cards = (layoutRef.current?.cards || []).map(c => c.id === cardId ? { ...c, ...updates } : c)
    const newLayout = { ...layoutRef.current, cards }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleRemoveCard = useCallback((cardId) => {
    const cards = (layoutRef.current?.cards || []).filter(c => c.id !== cardId)
    const newLayout = { ...layoutRef.current, cards }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleAddCard = useCallback((cardType, cardTypeInfo) => {
    const cards = layoutRef.current?.cards || []
    const targetSection = addCardTargetSection
      || (layoutRef.current?.sections?.[0]?.id)
      || 'system_status'
    const newCard = {
      id: `${cardType}_${Date.now()}`, type: cardType,
      title: cardTypeInfo?.label || cardType.toUpperCase().replace(/_/g,' '),
      section: targetSection,
      x: 0, y: 0, w: 1, h: 3, config: { refresh_seconds: 60 }
    }
    const newLayout = { ...layoutRef.current, cards: [...cards, newCard] }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave, addCardTargetSection])

  // ── Section management handlers ────────────────────────────────────────────

  const getSections = useCallback(() => {
    return layoutRef.current?.sections || DEFAULT_SECTIONS_DEF
  }, [])

  const handleAddSection = useCallback(() => {
    const sections = getSections()
    const id = `section_${Date.now()}`
    const newSection = { id, label: 'New Section', collapsed: false }
    const newLayout = { ...layoutRef.current, sections: [...sections, newSection] }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave, getSections])

  const handleRenameSection = useCallback((sectionId, newLabel) => {
    const sections = getSections().map(s => s.id === sectionId ? { ...s, label: newLabel } : s)
    const newLayout = { ...layoutRef.current, sections }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave, getSections])

  const handleToggleCollapse = useCallback((sectionId) => {
    const sections = getSections().map(s => s.id === sectionId ? { ...s, collapsed: !s.collapsed } : s)
    const newLayout = { ...layoutRef.current, sections }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave, getSections])

  const handleDeleteSection = useCallback((sectionId) => {
    const sections = getSections().filter(s => s.id !== sectionId)
    // Move orphaned cards to first remaining section or 'unsorted'
    const fallback = sections[0]?.id || 'unsorted'
    const cards = (layoutRef.current?.cards || []).map(c =>
      c.section === sectionId ? { ...c, section: fallback } : c
    )
    // Add unsorted section if needed and it doesn't exist
    let finalSections = sections
    if (fallback === 'unsorted' && !sections.find(s => s.id === 'unsorted')) {
      finalSections = [{ id: 'unsorted', label: 'Unsorted', collapsed: false }, ...sections]
    }
    const newLayout = { ...layoutRef.current, sections: finalSections, cards }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave, getSections])

  // SortableJS — card reordering within sections + section reordering
  useEffect(() => {
    if (!editMode) {
      sortablesRef.current.forEach(s => { try { s.destroy() } catch(e){} })
      sortablesRef.current = []
      if (sectionSortableRef.current) { try { sectionSortableRef.current.destroy() } catch(e){} sectionSortableRef.current = null }
      return
    }
    function initSortables() {
      // Destroy old card sortables
      sortablesRef.current.forEach(s => { try { s.destroy() } catch(e){} })
      sortablesRef.current = []
      // Card sortables — one per .noc-row; cross-section drag via group name
      document.querySelectorAll('.noc-row').forEach(row => {
        const s = window.Sortable?.create(row, {
          group: 'noc-cards',
          animation: 150,
          ghostClass: 'sortable-ghost',
          dragClass: 'sortable-drag',
          onEnd: (evt) => { saveCardOrderFromDOM(evt) }
        })
        if (s) sortablesRef.current.push(s)
      })
      // Section sortable — .noc-sections-container
      if (sectionSortableRef.current) { try { sectionSortableRef.current.destroy() } catch(e){} sectionSortableRef.current = null }
      const sectionsContainer = document.querySelector('.noc-sections-container')
      if (sectionsContainer) {
        sectionSortableRef.current = window.Sortable?.create(sectionsContainer, {
          handle: '.section-drag-handle',
          animation: 200,
          ghostClass: 'sortable-section-ghost',
          dragClass: 'sortable-section-drag',
          onEnd: () => { saveSectionOrderFromDOM() }
        })
      }
    }
    if (typeof window.Sortable !== 'undefined') {
      initSortables()
    } else {
      const script = document.createElement('script')
      script.src = 'https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js'
      script.onload = initSortables
      document.head.appendChild(script)
    }
    return () => {
      sortablesRef.current.forEach(s => { try { s.destroy() } catch(e){} })
      sortablesRef.current = []
      if (sectionSortableRef.current) { try { sectionSortableRef.current.destroy() } catch(e){} sectionSortableRef.current = null }
    }
  }, [editMode, layout?.sections?.length])  // re-init if section count changes

  function saveCardOrderFromDOM(evt) {
    // Read card order + section assignment from DOM
    const cards = []
    document.querySelectorAll('.noc-section-block').forEach(block => {
      const sectionId = block.dataset.sectionId
      block.querySelectorAll('.noc-card-slot').forEach(slot => {
        const id = slot.dataset.cardId
        const card = layoutRef.current?.cards?.find(c => c.id === id)
        if (card) cards.push({ ...card, section: sectionId })
      })
    })
    const extraCards = (layoutRef.current?.cards || []).filter(c => !cards.find(x => x.id === c.id))
    if (cards.length || extraCards.length) {
      const newLayout = { ...layoutRef.current, cards: [...cards, ...extraCards] }
      layoutRef.current = newLayout
      debouncedSave(newLayout)
    }
  }

  function saveSectionOrderFromDOM() {
    const ids = []
    document.querySelectorAll('.noc-section-block').forEach(block => {
      ids.push(block.dataset.sectionId)
    })
    const oldSections = layoutRef.current?.sections || DEFAULT_SECTIONS_DEF
    const reordered = ids.map(id => oldSections.find(s => s.id === id)).filter(Boolean)
    // Append any not in DOM
    oldSections.forEach(s => { if (!reordered.find(r => r.id === s.id)) reordered.push(s) })
    const newLayout = { ...layoutRef.current, sections: reordered }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }

  if (loading) {
    return <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', color:'var(--green,#00ff41)' }}>Initializing NOC Dashboard...</div>
  }

  const cards = (layout?.cards || []).filter(card => !isStandaloneHealthCard(card))
  const sections = layout?.sections?.length ? layout.sections : DEFAULT_SECTIONS_DEF

  // Group cards by section id
  const sectionMap = {}
  sections.forEach(s => { sectionMap[s.id] = [] })
  const unsortedCards = []
  for (const card of cards) {
    const sid = cardSectionId(card)
    if (sectionMap[sid] !== undefined) sectionMap[sid].push(card)
    else unsortedCards.push(card)
  }

  // Ticker items
  const tickerItems = []
  for (const card of cards) {
    const d = cardData[card.type]
    if (!d) continue
    const st = d.state
    if (st === 'crit' || st === 'critical' || st === 'error') tickerItems.push({ text: d.note || d.error || `${card.title} CRITICAL`, level: 'crit' })
    else if (st === 'warn') tickerItems.push({ text: d.note || `${card.title} warning`, level: 'warn' })
  }
  const tickerDisplay = [...tickerItems, ...tickerItems]
  const tickerWorst = tickerItems.some(i => i.level === 'crit') ? 'crit' : tickerItems.some(i => i.level === 'warn') ? 'warn' : 'ok'
  const themeLabel = (layout?.theme || 'dark-noc').toUpperCase().replace(/-/g,' ')
  const overallTxt = overallHealth === 'crit' ? 'CRITICAL' : overallHealth === 'warn' ? 'WARNING' : 'ALL SYSTEMS OK'
  const alertItems = tickerItems

  // Helper: render one section block
  function renderSection(section, isExtra = false) {
    const sectionCards = isExtra ? unsortedCards : (sectionMap[section.id] || [])

    // In edit mode, always render even if empty (user may want to add cards)
    if (!editMode && sectionCards.length === 0 && !section.panelbox && !section.historyPanel && !section.certsPanel) return null

    const collapsed = section.collapsed

    return (
      <div
        key={section.id}
        className="noc-section-block"
        data-section-id={section.id}
        style={{ marginBottom: collapsed && !editMode ? 0 : undefined }}
      >
        <SectionHeader
          section={section}
          editMode={editMode}
          onRename={handleRenameSection}
          onDelete={handleDeleteSection}
          onToggleCollapse={handleToggleCollapse}
        />

        {!collapsed && (
          <>
            {/* Proxmox Storage — panelbox with donut gauges */}
            {section.panelbox && !section.historyPanel && !section.certsPanel && (() => {
              const pxCard = sectionCards[0]
              const pxData = pxCard ? cardData[pxCard.type] : null
              return (
                <>
                  <ProxmoxStoragePanel data={pxData} />
                  {pxCard && (
                    <div style={{display:'none'}}>
                      <CardWrapper card={pxCard} onUpdate={handleUpdateCard} onRemove={handleRemoveCard} onData={handleCardData} editMode={false} />
                    </div>
                  )}
                </>
              )
            })()}

            {/* Uptime History — panelbox with hbar rows */}
            {section.historyPanel && (() => {
              const ukCard = sectionCards[0]
              const ukData = ukCard ? cardData[ukCard.type] : cardData['uptime_kuma']
              return (
                <>
                  <UptimeHistoryPanel data={ukData} />
                  {ukCard && (
                    <div style={{display:'none'}}>
                      <CardWrapper card={ukCard} onUpdate={handleUpdateCard} onRemove={handleRemoveCard} onData={handleCardData} editMode={false} />
                    </div>
                  )}
                </>
              )
            })()}

            {/* Certs & Alerts — twocol panelboxes */}
            {section.certsPanel && (
              <CertsAlertsPanel
                nginxData={cardData['nginx_proxy']}
                uptimeData={cardData['uptime_kuma']}
                alertItems={alertItems}
              />
            )}

            {/* Normal card grid */}
            {!section.panelbox && !section.historyPanel && !section.certsPanel && (
              <div className={`row noc-row${editMode ? ' edit-active' : ''}`}>
                {sectionCards.map(card => (
                  <div key={card.id} className="noc-card-slot" data-card-id={card.id}>
                    <CardWrapper
                      card={card}
                      onUpdate={handleUpdateCard}
                      onRemove={handleRemoveCard}
                      onOpenSettings={editMode ? setSettingsCard : null}
                      onData={handleCardData}
                      editMode={editMode}
                    />
                  </div>
                ))}
                {editMode && sectionCards.length === 0 && (
                  <div style={{ color: 'var(--muted)', fontSize: 11, padding: '12px 4px', fontStyle: 'italic', letterSpacing: '1px' }}>
                    Empty section — use + ADD CARD in the navbar
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    )
  }



  function enterEditMode() {
    editSnapshotRef.current = layoutRef.current ? JSON.parse(JSON.stringify(layoutRef.current)) : null
    setEditMode(true)
  }

  function saveEditMode() {
    if (layoutRef.current) saveLayout(layoutRef.current).catch(() => {})
    editSnapshotRef.current = null
    setEditMode(false)
  }

  function cancelEditMode() {
    if (editSnapshotRef.current) {
      const restored = editSnapshotRef.current
      setLayout(restored)
      layoutRef.current = restored
    }
    editSnapshotRef.current = null
    setEditMode(false)
    setShowAdd(false)
    setAddCardTargetSection(null)
  }

  function toggleEditFromMenu() {
    if (editMode) saveEditMode()
    else enterEditMode()
  }

  return (
    <div>
      {/* Topbar */}
      <div className="topbar">
        <div className="brand">
          <h1>{config?.title || 'MRDTech Homelab'}</h1>
          <span className="tag">{config?.subtitle || 'NOC // ANTON'}</span>
        </div>
        <div className="top-right">
          <div className="ts">UPDATED <b>{lastUpdated ? formatDate(lastUpdated) : '—'}</b></div>
          <div className={`health h-${overallHealth}`}><span className="led" />{overallTxt}</div>
          <button className="theme-btn nav-icon-btn" onClick={() => setShowAlerts(true)} title="Alert history" aria-label="Alert history">🔔{alertItems.length > 0 && <span className="bell-badge" style={{ display:'inline-block' }}>{alertItems.length}</span>}</button>
          <button className="theme-btn nav-icon-btn" onClick={() => setShowIntel(true)} title="NOC Intelligence" aria-label="NOC Intelligence"><svg className="nav-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-5"/><path d="M12 16V8"/><path d="M16 16v-7"/><path d="M20 16v-3"/></svg></button>
          {editMode && (
            <>
              <button className="theme-btn" onClick={saveEditMode} title="Save layout" style={{ background:'var(--green)', color:'#000', border:'none', fontWeight:700 }}>✓ SAVE</button>
              <button className="theme-btn" onClick={cancelEditMode} title="Cancel edit mode without saving" style={{ borderColor:'var(--crit)', color:'var(--crit)' }}>✕ CANCEL</button>
              <button className="theme-btn" onClick={() => { setAddCardTargetSection(null); setShowAdd(true) }} title="Add card" style={{ background:'var(--green)', color:'#000', border:'none', fontWeight:700 }}>+ ADD CARD</button>
            </>
          )}
          <div className="gear-menu" ref={gearMenuRef}>
            <button
              className="theme-btn nav-icon-btn"
              onClick={() => setGearMenuOpen(o => !o)}
              title="Dashboard menu"
              aria-label="Dashboard menu"
            >
              ⚙▾
            </button>
            {gearMenuOpen && (
              <div className="user-dropdown gear-dropdown">
                <div className="user-dropdown-id" aria-label="Signed in user">
                  <b>{authUser.username || 'admin'}</b>
                  <span>{authUser.role || 'Administrator'}</span>
                </div>
                <div className="user-dropdown-divider" />
                <button onClick={() => { setGearMenuOpen(false); handleLogout() }}>Logout</button>
                <button onClick={() => { toggleEditFromMenu(); setGearMenuOpen(false) }}>{editMode ? 'Save Editing' : 'Edit Dashboard'}</button>
                <button onClick={() => { setShowIntegrations(true); setGearMenuOpen(false) }}>Settings</button>
              </div>
            )}
          </div>
          <button className="theme-btn nav-icon-btn" onClick={cycleTheme} title={`Cycle theme (${themeLabel})`} aria-label={`Cycle theme (${themeLabel})`}>🌙</button>
        </div>
      </div>

      {/* Ticker */}
      <div className="ticker-bar">
        <div className={`tk-badge tb-${tickerWorst}`}>{tickerWorst === 'crit' ? 'ALERT' : tickerWorst === 'warn' ? 'WARN' : 'OK'}</div>
        <div className="tk-track">
          <div className="tk-content" id="tk-content">
            {tickerDisplay.length === 0 ? (
              <span className="tk-item t-ok">All systems nominal</span>
            ) : tickerDisplay.map((item, i) => (
              <React.Fragment key={i}>
                <span className={`tk-item t-${item.level}`}>{item.text}</span>
                {i < tickerDisplay.length - 1 && <span className="tk-sep">◆</span>}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="wrap">
        <div className="noc-sections-container">
          {sections.map(section => renderSection(section))}
          {unsortedCards.length > 0 && renderSection(
            { id: '__unsorted__', label: 'Other', collapsed: false },
            true
          )}
        </div>
      </div>

      <footer>MRDTECH INFRASTRUCTURE MONITORING · AUTO-REFRESH 60s · REGEN 15m</footer>

      {showAlerts && (
        <>
          <div className="alert-overlay" style={{ display:'block' }} onClick={(e) => { if (isGenuineBackdropClick(e, '.alert-panel')) setShowAlerts(false) }} />
          <aside className="alert-panel open">
            <div className="alert-panel-hdr"><span>ALERT HISTORY</span><button onClick={() => setShowAlerts(false)}>×</button></div>
            {alertItems.length === 0 ? (
              <div className="alert-panel-empty">No active alerts. Anton remains disappointed by the lack of drama.</div>
            ) : (
              <ul className="alert-feed">
                {alertItems.map((item, i) => <li key={i}><span className="ah-ts">CURRENT</span><span className="ah-text">{item.text}</span></li>)}
              </ul>
            )}
          </aside>
        </>
      )}

      {/* Card modal */}
      <div id="card-modal" className="card-modal" onClick={e => { if (isGenuineBackdropClick(e, '.card-modal-box')) document.getElementById('card-modal').style.display='none' }} style={{ display:'none' }}>
        <div className="card-modal-box">
          <button className="card-modal-close" onClick={() => document.getElementById('card-modal').style.display='none'}>×</button>
          <div id="card-modal-title" className="card-modal-title"></div>
          <div id="card-modal-body" className="card-modal-body"></div>
        </div>
      </div>

      {editMode && (
        <div style={{ position:'fixed', bottom:16, left:'50%', transform:'translateX(-50%)', background:'rgba(0,0,0,0.9)', border:'1px solid var(--green)', borderRadius:4, padding:'6px 20px', fontSize:11, color:'var(--green)', letterSpacing:'0.1em', zIndex:1000, pointerEvents:'none', fontFamily:'inherit' }}>
          EDIT MODE — Drag cards to reorder · ⠿ Drag section header to reorder sections · Click section name to rename · ✕ to remove
        </div>
      )}

      {showAdd && (
        <AddCardPanel
          onAdd={(type, info) => { handleAddCard(type, info); setShowAdd(false) }}
          onClose={() => setShowAdd(false)}
        />
      )}

      {settingsCard && (
        <SettingsPanel
          card={settingsCard}
          onSave={(updates) => { handleUpdateCard(settingsCard.id, updates); setSettingsCard(null) }}
          onRemove={() => { handleRemoveCard(settingsCard.id); setSettingsCard(null) }}
          onClose={() => setSettingsCard(null)}
          sections={sections}
        />
      )}

      {showIntegrations && (
        <IntegrationsPage onClose={() => setShowIntegrations(false)} />
      )}

      <IntelligencePanel open={showIntel} onClose={() => setShowIntel(false)} intelligence={intelligence} onOpenHealth={() => setShowHealthDetail(true)} />

      {showHealthDetail && (
        <HealthDetailModal intelligence={intelligence} onClose={() => setShowHealthDetail(false)} />
      )}

      {firstLaunch && !showIntegrations && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:2000 }}>
          <div style={{ background:'var(--panel)', border:'1px solid var(--line)', borderRadius:8, padding:'32px 40px', maxWidth:440, textAlign:'center' }}>
            <div style={{
              color: 'var(--green)', fontSize: 16, letterSpacing: '0.06em', marginBottom: 10,
            }}>
              Welcome to NOC Dashboard
            </div>
            <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.7, marginBottom: 24 }}>
              No integrations configured yet. Add your first integration to start
              pulling live data into your cards. Click Settings to get started.
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <button
                className="btn-accent"
                style={{ fontSize: 12, padding: '8px 24px' }}
                onClick={() => setShowIntegrations(true)}
              >
                ⚙ Open Settings
              </button>
              <button
                className="btn-ghost"
                style={{ fontSize: 12, padding: '8px 16px' }}
                onClick={() => setFirstLaunch(false)}
              >
                Skip for now
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
