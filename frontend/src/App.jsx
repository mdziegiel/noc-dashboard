import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fetchLayout, fetchThemes, fetchConfig, saveLayout, fetchFirstLaunch } from './api.js'
import CardWrapper from './components/CardWrapper.jsx'
import AddCardPanel from './components/AddCardPanel.jsx'
import SettingsPanel from './components/SettingsPanel.jsx'
import IntegrationsPage from './components/IntegrationsPage.jsx'

// Section definitions matching generate_dashboard.py exactly
const SECTION_ORDER = [
  { label: 'System Status', types: ['wan_health','proxmox','home_assistant','uptime_kuma','docker','pbs','urbackup','smart_health'] },
  { label: 'Security & Network', types: ['unifi','nginx_proxy','cloudflare','wazuh','crowdsec','limacharlie','adguard','adguard2','tailscale','malware_sources','wan_health_sec'] },
  { label: 'Media & Downloads', types: ['plex','tautulli','sonarr','radarr','sabnzbd','overseerr','prowlarr'] },
  { label: 'Storage', types: ['qnap','proxmox_storage'] },
  { label: 'Monitoring', types: ['uptime_kuma_detail','custom_url'] },
]

function cardSection(type) {
  for (const s of SECTION_ORDER) {
    if (s.types.includes(type)) return s.label
  }
  return 'Monitoring'
}

function formatDate(d) {
  if (!d) return '—'
  return d.toLocaleDateString('en-US', { weekday:'short', month:'short', day:'numeric', year:'numeric' })
    + ' ' + d.toLocaleTimeString('en-US', { hour:'2-digit', minute:'2-digit', timeZoneName:'short' })
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

export default function App() {
  const [layout, setLayout] = useState(null)
  const [config, setConfig] = useState({})
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showIntegrations, setShowIntegrations] = useState(false)
  const [firstLaunch, setFirstLaunch] = useState(false)
  const [cardData, setCardData] = useState({})
  const [settingsCard, setSettingsCard] = useState(null)
  const [overallHealth, setOverallHealth] = useState('ok')
  const saveTimerRef = useRef(null)
  const layoutRef = useRef(null)
  const sortablesRef = useRef([])

  useEffect(() => {
    Promise.all([fetchLayout(), fetchConfig(), fetchFirstLaunch()])
      .then(([lay, cfg, fl]) => {
        setLayout(lay); setConfig(cfg)
        setLastUpdated(new Date())
        layoutRef.current = lay
        applyThemeAttr('dark-noc') // always dark-noc on load; auto-switch permanently removed
        setLoading(false)
        if (fl?.first_launch) {
          setFirstLaunch(true)
        }
      })
      .catch(() => setLoading(false))
  }, [])

  // Auto theme switch REMOVED — dark-noc is permanent. Timer block deleted.
  // Manual cycling still works via cycleTheme() below.


  // applyThemeAttr: dark-noc is always the default (no data-theme attr).
  // Manual switching via cycle button is still supported, but on every page load
  // we unconditionally apply dark-noc. The name param is used only for manual cycling.
  function applyThemeAttr(name) {
    const themeMap = { 'dark-noc': '', 'light-clean': 'light', 'midnight-blue': 'midnight', 'solarized-dark': 'solarized', 'dracula': 'dracula', 'nord': 'nord', 'gruvbox': 'gruvbox', 'tokyo': 'tokyo' }
    const attr = themeMap[name] ?? ''
    if (attr) { document.documentElement.setAttribute('data-theme', attr); document.body.setAttribute('data-theme', attr) }
    else { document.documentElement.removeAttribute('data-theme'); document.body.removeAttribute('data-theme') }
  }

  function cycleTheme() {
    const names = ['dark-noc','light-clean','midnight-blue','solarized-dark','dracula','nord','gruvbox']
    const cur = layoutRef.current?.theme || 'dark-noc'
    const next = names[(names.indexOf(cur) + 1) % names.length]
    const newLayout = { ...layoutRef.current, theme: next }
    setLayout(newLayout); layoutRef.current = newLayout
    applyThemeAttr(next)
    debouncedSave(newLayout)
  }

  // Compute overall health from card data
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
    setCardData(prev => ({ ...prev, [cardType]: data }))
  }, [])

  const debouncedSave = useCallback((newLayout) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
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
    const newCard = {
      id: `${cardType}_${Date.now()}`, type: cardType,
      title: cardTypeInfo?.label || cardType.toUpperCase(),
      x: 0, y: 0, w: 1, h: 3, config: { refresh_seconds: 60 }
    }
    const newLayout = { ...layoutRef.current, cards: [...cards, newCard] }
    setLayout(newLayout); layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  // SortableJS edit mode
  useEffect(() => {
    if (!editMode) {
      sortablesRef.current.forEach(s => { try { s.destroy() } catch(e){} })
      sortablesRef.current = []
      return
    }
    function initSortables() {
      sortablesRef.current.forEach(s => { try { s.destroy() } catch(e){} })
      sortablesRef.current = []
      document.querySelectorAll('.noc-row').forEach(row => {
        const s = window.Sortable?.create(row, {
          animation: 150, ghostClass: 'sortable-ghost', dragClass: 'sortable-drag',
          onEnd: () => { saveOrderFromDOM() }
        })
        if (s) sortablesRef.current.push(s)
      })
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
    }
  }, [editMode])

  function saveOrderFromDOM() {
    const cards = []
    let y = 0
    document.querySelectorAll('.noc-row .noc-card-slot').forEach(slot => {
      const id = slot.dataset.cardId
      const card = layoutRef.current?.cards?.find(c => c.id === id)
      if (card) cards.push({ ...card, y: y++ })
    })
    if (cards.length) {
      const newLayout = { ...layoutRef.current, cards }
      layoutRef.current = newLayout
      debouncedSave(newLayout)
    }
  }

  if (loading) {
    return <div style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'100vh', color:'var(--green,#00ff41)' }}>Initializing NOC Dashboard...</div>
  }

  const cards = layout?.cards || []

  // Group cards into sections preserving order within each section
  const sectionMap = {}
  SECTION_ORDER.forEach(s => { sectionMap[s.label] = [] })
  const extraCards = []
  for (const card of cards) {
    const sec = cardSection(card.type)
    if (sectionMap[sec]) sectionMap[sec].push(card)
    else extraCards.push(card)
  }

  // Ticker items from card data
  const tickerItems = []
  for (const card of cards) {
    const d = cardData[card.type]
    if (!d) continue
    const st = d.state
    if (st === 'crit' || st === 'critical' || st === 'error') tickerItems.push({ text: d.note || d.error || `${card.title} CRITICAL`, level: 'crit' })
    else if (st === 'warn') tickerItems.push({ text: d.note || `${card.title} warning`, level: 'warn' })
  }
  const tickerWorst = tickerItems.some(i => i.level === 'crit') ? 'crit' : tickerItems.some(i => i.level === 'warn') ? 'warn' : 'ok'
  const themeLabel = (layout?.theme || 'dark-noc').toUpperCase().replace(/-/g,' ')
  const overallTxt = overallHealth === 'crit' ? 'CRITICAL' : overallHealth === 'warn' ? 'WARNING' : 'ALL SYSTEMS OK'

  return (
    <div>
      {/* Topbar — exact structure from generate_dashboard.py */}
      <div className="topbar">
        <div className="brand">
          <h1>{config?.title || 'MRDTech Homelab'}</h1>
          <span className="tag">{config?.subtitle || 'NOC // ANTON'}</span>
        </div>
        <div className="top-right">
          <div className="ts">UPDATED <b>{lastUpdated ? formatDate(lastUpdated) : '—'}</b></div>
          <div className={`health h-${overallHealth}`}><span className="led" />{overallTxt}</div>
          <button
            className="theme-btn"
            onClick={() => setShowIntegrations(true)}
            title="Settings / Integrations"
            style={{ padding: '3px 8px' }}
          >
            ⚙
          </button>
          <button className={`theme-btn${editMode ? ' active' : ''}`} onClick={() => setEditMode(m => !m)} title="Edit card layout">
            {editMode ? '✓ DONE' : '✎ EDIT'}
          </button>
          {editMode && (
            <button className="theme-btn" onClick={() => setShowAdd(true)} title="Add card" style={{ background:'var(--green)', color:'#000', border:'none', fontWeight:700 }}>
              + ADD
            </button>
          )}
          <button className="theme-btn" onClick={cycleTheme} title="Cycle theme">◐ {themeLabel}</button>
        </div>
      </div>

      {/* Ticker */}
      <div className="ticker-bar">
        <div className={`tk-badge tb-${tickerWorst}`}>{tickerWorst === 'crit' ? 'ALERT' : tickerWorst === 'warn' ? 'WARN' : 'OK'}</div>
        <div className="tk-track">
          <div className="tk-content" id="tk-content">
            {tickerItems.length === 0 ? (
              <span className="tk-item t-ok">All systems nominal</span>
            ) : tickerItems.map((item, i) => (
              <React.Fragment key={i}>
                <span className={`tk-item t-${item.level}`}>{item.text}</span>
                {i < tickerItems.length - 1 && <span className="tk-sep">◆</span>}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>

      {/* Main content — section-label + row structure */}
      <div className="wrap">
        {SECTION_ORDER.map(section => {
          const sectionCards = sectionMap[section.label] || []
          if (sectionCards.length === 0) return null
          return (
            <React.Fragment key={section.label}>
              <div className="section-label">{section.label}</div>
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
              </div>
            </React.Fragment>
          )
        })}
        {extraCards.length > 0 && (
          <>
            <div className="section-label">Other</div>
            <div className="row noc-row">
              {extraCards.map(card => (
                <div key={card.id} className="noc-card-slot" data-card-id={card.id}>
                  <CardWrapper card={card} onUpdate={handleUpdateCard} onRemove={handleRemoveCard} onOpenSettings={editMode ? setSettingsCard : null} onData={handleCardData} editMode={editMode} />
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <footer>MRDTECH INFRASTRUCTURE MONITORING · AUTO-REFRESH 60s · REGEN 15m</footer>

      {/* Card modal */}
      <div id="card-modal" className="card-modal" onClick={e => { if (e.target.id==='card-modal') document.getElementById('card-modal').style.display='none' }} style={{ display:'none' }}>
        <div className="card-modal-box">
          <button className="card-modal-close" onClick={() => document.getElementById('card-modal').style.display='none'}>×</button>
          <div id="card-modal-title" className="card-modal-title"></div>
          <div id="card-modal-body" className="card-modal-body"></div>
        </div>
      </div>

      {editMode && (
        <div style={{ position:'fixed', bottom:16, left:'50%', transform:'translateX(-50%)', background:'rgba(0,0,0,0.9)', border:'1px solid var(--green)', borderRadius:4, padding:'6px 20px', fontSize:11, color:'var(--green)', letterSpacing:'0.1em', zIndex:1000, pointerEvents:'none', fontFamily:'inherit' }}>
          EDIT MODE — Drag cards to reorder · ⚙ to configure · ✕ to remove
        </div>
      )}

      {showAdd && (
        <AddCardPanel onAdd={(type, info) => { handleAddCard(type, info); setShowAdd(false) }} onClose={() => setShowAdd(false)} />
      )}
      {settingsCard && (
        <SettingsPanel card={settingsCard} onSave={updates => { handleUpdateCard(settingsCard.id, updates); setSettingsCard(null) }} onRemove={id => { handleRemoveCard(id); setSettingsCard(null) }} onClose={() => setSettingsCard(null)} />
      )}
      {showIntegrations && (
        <IntegrationsPage onClose={() => { setShowIntegrations(false); setFirstLaunch(false) }} />
      )}
      {firstLaunch && !showIntegrations && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 400,
          background: 'rgba(0,0,0,0.88)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          animation: 'fadeIn 0.2s ease',
        }}>
          <div style={{
            background: 'var(--panel)', border: '1px solid var(--green)',
            borderRadius: 6, padding: '36px 48px', maxWidth: 460, textAlign: 'center',
            boxShadow: '0 0 40px rgba(0,255,65,0.15)',
          }}>
            <div style={{ fontSize: 28, marginBottom: 12 }}>⚡</div>
            <div style={{
              fontSize: 16, fontWeight: 700, color: 'var(--green)',
              letterSpacing: '0.06em', marginBottom: 10,
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
