import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fetchLayout, fetchThemes, fetchConfig, saveLayout } from './api.js'
import GridLayout from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import CardWrapper from './components/CardWrapper.jsx'
import AddCardPanel from './components/AddCardPanel.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'

// Map card type -> section label (matches generate_dashboard.py section order)
const SECTION_MAP = {
  wan_health:     'System Status',
  proxmox:        'System Status',
  home_assistant: 'System Status',
  uptime_kuma:    'System Status',
  docker:         'System Status',
  pbs:            'System Status',
  urbackup:       'System Status',
  smart_health:   'System Status',
  unifi:          'Security & Network',
  nginx_proxy:    'Security & Network',
  cloudflare:     'Security & Network',
  wazuh:          'Security & Network',
  crowdsec:       'Security & Network',
  limacharlie:    'Security & Network',
  adguard:        'Security & Network',
  tailscale:      'Security & Network',
  malware_sources:'Security & Network',
  plex:           'Media & Downloads',
  tautulli:       'Media & Downloads',
  sonarr:         'Media & Downloads',
  radarr:         'Media & Downloads',
  sabnzbd:        'Media & Downloads',
  overseerr:      'Media & Downloads',
  prowlarr:       'Media & Downloads',
  qnap:           'Storage',
  proxmox_storage:'Storage',
  custom_url:     'Monitoring',
}

const COLS = 4
const ROW_HEIGHT = 60
const MARGIN = [12, 12]

function formatDate(d) {
  if (!d) return ''
  return d.toLocaleDateString('en-US', { weekday:'short', month:'short', day:'numeric', year:'numeric' })
    + ' ' + d.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', timeZoneName:'short' })
}

function HealthBadge({ cards, cardData }) {
  // Compute worst state across all cards with data
  let worst = 'ok'
  for (const card of cards) {
    const data = cardData[card.type]
    const state = data?.state
    if (state === 'crit' || state === 'critical' || state === 'error') { worst = 'crit'; break }
    if (state === 'warn' && worst !== 'crit') worst = 'warn'
  }
  const label = worst === 'crit' ? 'CRITICAL' : worst === 'warn' ? 'WARNING' : 'ALL SYSTEMS OK'
  return (
    <div className={`health h-${worst}`}>
      <span className="led" />
      {label}
    </div>
  )
}

function TickerBar({ cards, cardData }) {
  // Build ticker items from alerts/warnings in card data
  const items = []
  for (const card of cards) {
    const data = cardData[card.type]
    if (!data) continue
    const st = data.state
    if (st === 'crit' || st === 'critical' || st === 'error') {
      const note = data.note || data.error || `${card.title} ${st}`
      items.push({ text: note, level: 'crit' })
    } else if (st === 'warn') {
      const note = data.note || `${card.title} warning`
      items.push({ text: note, level: 'warn' })
    }
  }

  const worst = items.some(i => i.level === 'crit') ? 'crit'
              : items.some(i => i.level === 'warn') ? 'warn' : 'ok'

  if (items.length === 0) {
    return (
      <div className="ticker-bar">
        <div className={`tk-badge tb-${worst}`}>OK</div>
        <div className="tk-track">
          <div className="tk-content" id="tk-content">
            <span className="tk-item t-ok">All systems nominal</span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="ticker-bar">
      <div className={`tk-badge tb-${worst}`}>{worst === 'crit' ? 'ALERT' : 'WARN'}</div>
      <div className="tk-track">
        <div className="tk-content" id="tk-content">
          {items.map((item, i) => (
            <React.Fragment key={i}>
              <span className={`tk-item t-${item.level}`}>{item.text}</span>
              {i < items.length - 1 && <span className="tk-sep">◆</span>}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [layout, setLayout] = useState(null)
  const [themes, setThemes] = useState({})
  const [config, setConfig] = useState({})
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [cardData, setCardData] = useState({})        // card.type -> latest data
  const [settingsCard, setSettingsCard] = useState(null)
  const [containerWidth, setContainerWidth] = useState(
    typeof window !== 'undefined' ? window.innerWidth - MARGIN[0] * 2 : 1200
  )
  const saveTimerRef = useRef(null)
  const layoutRef = useRef(null)

  useEffect(() => {
    function handleResize() { setContainerWidth(window.innerWidth - MARGIN[0] * 2) }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    Promise.all([fetchLayout(), fetchThemes(), fetchConfig()])
      .then(([lay, thms, cfg]) => {
        setLayout(lay); setThemes(thms); setConfig(cfg)
        setLastUpdated(new Date())
        layoutRef.current = lay
        // Apply theme via data-theme attribute on <html>
        const themeName = lay?.theme || 'dark-noc'
        applyThemeAttr(themeName)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  // Auto theme switch
  useEffect(() => {
    if (!layout?.autoTheme) return
    const t = setInterval(() => {
      const lay = layoutRef.current
      if (!lay) return
      const hour = new Date().getHours()
      const dayStart = lay.dayStart ?? 7
      const nightStart = lay.nightStart ?? 19
      const themeName = (hour >= dayStart && hour < nightStart)
        ? (lay.dayTheme || lay.theme)
        : (lay.nightTheme || lay.theme)
      applyThemeAttr(themeName)
    }, 60000)
    return () => clearInterval(t)
  }, [layout?.autoTheme])

  const debouncedSave = useCallback((newLayout) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      saveLayout(newLayout).catch(() => {})
    }, 500)
  }, [])

  function applyThemeAttr(name) {
    // Map theme names to data-theme attribute values used in CSS
    const themeMap = {
      'dark-noc': '',         // default (no attribute = dark)
      'light-clean': 'light',
      'midnight-blue': 'midnight',
      'solarized-dark': 'solarized',
      'dracula': 'dracula',
      'nord': 'nord',
      'gruvbox': 'gruvbox',
      'tokyo': 'tokyo',
    }
    const attr = themeMap[name] ?? ''
    if (attr) {
      document.documentElement.setAttribute('data-theme', attr)
    } else {
      document.documentElement.removeAttribute('data-theme')
    }
    // Store on body too (reference uses body[data-theme] in some places)
    if (attr) {
      document.body.setAttribute('data-theme', attr)
    } else {
      document.body.removeAttribute('data-theme')
    }
  }

  function cycleTheme() {
    const themeNames = ['dark-noc','light-clean','midnight-blue','solarized-dark','dracula','nord','gruvbox']
    const cur = layout?.theme || 'dark-noc'
    const idx = themeNames.indexOf(cur)
    const next = themeNames[(idx + 1) % themeNames.length]
    const newLayout = { ...layoutRef.current, theme: next }
    setLayout(newLayout); layoutRef.current = newLayout
    applyThemeAttr(next)
    debouncedSave(newLayout)
  }

  // Receive data back from CardWrapper children
  const handleCardData = useCallback((cardType, data) => {
    setCardData(prev => ({ ...prev, [cardType]: data }))
  }, [])

  const handleLayoutChange = useCallback((newLayout) => {
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleGridChange = useCallback((newItems) => {
    const cards = layoutRef.current?.cards || []
    const posMap = {}
    newItems.forEach(item => { posMap[item.i] = item })
    const updatedCards = cards.map(card => {
      const pos = posMap[card.id]
      if (!pos) return card
      return { ...card, x: pos.x, y: pos.y, w: pos.w, h: pos.h }
    })
    const newLayout = { ...layoutRef.current, cards: updatedCards }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleAddCard = useCallback((cardType, cardTypeInfo) => {
    const cards = layoutRef.current?.cards || []
    const maxY = cards.reduce((m, c) => Math.max(m, (c.y || 0) + (c.h || 3)), 0)
    const newCard = {
      id: `${cardType}_${Date.now()}`,
      type: cardType,
      title: cardTypeInfo?.label || cardType.toUpperCase(),
      x: 0, y: maxY, w: 1, h: 3,
      config: { refresh_seconds: 60 },
    }
    const newLayout = { ...layoutRef.current, cards: [...cards, newCard] }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleUpdateCard = useCallback((cardId, updates) => {
    const cards = (layoutRef.current?.cards || []).map(c =>
      c.id === cardId ? { ...c, ...updates } : c
    )
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

  if (loading) {
    return (
      <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', color:'var(--green,#00ff41)' }}>
        Initializing NOC Dashboard...
      </div>
    )
  }

  const cards = layout?.cards || []

  // Group cards into sections by y-position order
  const sortedCards = [...cards].sort((a, b) => a.y !== b.y ? a.y - b.y : a.x - b.x)

  // Build sections in the order defined by SECTION_MAP (preserving fixed section order)
  const SECTION_ORDER = [
    'System Status',
    'Security & Network',
    'Media & Downloads',
    'Storage',
    'Monitoring',
  ]

  // Build sections map from sorted cards
  const sectionCards = {}
  SECTION_ORDER.forEach(s => { sectionCards[s] = [] })
  const customSection = {}
  for (const card of sortedCards) {
    const section = SECTION_MAP[card.type] || 'Monitoring'
    if (!sectionCards[section]) sectionCards[section] = []
    sectionCards[section].push(card)
  }

  // Build RGL grid items
  const gridItems = cards.map(card => ({
    i: card.id, x: card.x ?? 0, y: card.y ?? 0, w: card.w ?? 1, h: card.h ?? 3,
  }))

  const themeLabel = (layout?.theme || 'dark-noc').toUpperCase().replace(/-/g, ' ')

  return (
    <div>
      {/* Topbar — exact structure from generate_dashboard.py */}
      <div className="topbar">
        <div className="brand">
          <h1>{config?.title || 'MRDTech Homelab'}</h1>
          <span className="tag">{config?.subtitle || 'NOC // ANTON'}</span>
        </div>
        <div className="top-right">
          <div className="ts">
            UPDATED <b>{lastUpdated ? formatDate(lastUpdated) : '—'}</b>
          </div>
          <HealthBadge cards={cards} cardData={cardData} />
          {/* Edit mode toggle — replaces alert bell slot */}
          <button
            className="theme-btn"
            onClick={() => setEditMode(m => !m)}
            title={editMode ? 'Exit Edit Mode' : 'Edit Layout'}
            style={{ color: editMode ? 'var(--green)' : undefined, borderColor: editMode ? 'var(--green)' : undefined }}
          >
            {editMode ? '✓ EDITING' : '✎ EDIT'}
          </button>
          {editMode && (
            <button className="theme-btn" onClick={() => setShowAdd(true)} title="Add card"
              style={{ background:'var(--green)', color:'#000', border:'none', fontWeight:700 }}>
              + ADD
            </button>
          )}
          <button
            className="theme-btn"
            onClick={cycleTheme}
            title="Cycle theme"
          >
            &#9680; {themeLabel}
          </button>
        </div>
      </div>

      {/* Ticker bar */}
      <TickerBar cards={cards} cardData={cardData} />

      {/* Main grid — react-grid-layout filling the wrap div */}
      <div className="wrap" style={{ padding: 0 }}>
        <GridLayout
          className="layout"
          layout={gridItems}
          cols={COLS}
          rowHeight={ROW_HEIGHT}
          width={containerWidth}
          margin={MARGIN}
          draggableHandle=".card-drag-handle"
          onLayoutChange={handleGridChange}
          isDraggable={editMode}
          isResizable={editMode}
          useCSSTransforms={true}
          style={{ minHeight: 400 }}
        >
          {cards.map(card => (
            <div key={card.id}>
              <CardWrapper
                card={card}
                onUpdate={handleUpdateCard}
                onRemove={handleRemoveCard}
                onOpenSettings={setSettingsCard}
                onData={handleCardData}
                editMode={editMode}
              />
            </div>
          ))}
        </GridLayout>
      </div>

      <footer>MRDTECH INFRASTRUCTURE MONITORING · AUTO-REFRESH 60s · REGEN 15m</footer>

      {/* Card modal (reference feature — focus a card) */}
      <div id="card-modal" className="card-modal" onClick={e => {
        if (e.target.id === 'card-modal') { e.currentTarget.style.display = 'none' }
      }} style={{ display: 'none' }}>
        <div className="card-modal-box">
          <button className="card-modal-close" onClick={() => document.getElementById('card-modal').style.display='none'}>×</button>
          <div id="card-modal-title" className="card-modal-title"></div>
          <div id="card-modal-body" className="card-modal-body"></div>
        </div>
      </div>

      {/* Alert panel */}
      <div id="alert-overlay" className="alert-overlay" onClick={() => {
        document.getElementById('alert-panel')?.classList.remove('open')
        document.getElementById('alert-overlay').style.display = 'none'
      }} style={{ display: 'none' }} />
      <div id="alert-panel" className="alert-panel">
        <div className="alert-panel-hdr">
          <span>ALERT HISTORY</span>
          <button onClick={() => document.getElementById('alert-panel')?.classList.remove('open')}>×</button>
        </div>
        <ul id="alert-feed" className="alert-feed"></ul>
        <div className="alert-panel-empty" id="alert-empty">No alert history recorded yet.</div>
      </div>

      {/* Edit mode bottom banner */}
      {editMode && (
        <div className="edit-mode-banner">
          EDIT MODE — Drag cards · Resize corners · ⚙ to configure · ✕ to remove
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
          onSave={updates => { handleUpdateCard(settingsCard.id, updates); setSettingsCard(null) }}
          onRemove={id => { handleRemoveCard(id); setSettingsCard(null) }}
          onClose={() => setSettingsCard(null)}
        />
      )}
    </div>
  )
}
