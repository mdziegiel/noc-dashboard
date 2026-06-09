import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fetchLayout, fetchThemes, fetchConfig, saveLayout } from './api.js'
import { applyTheme, resolveTheme } from './theme.js'
import TopBar from './components/TopBar.jsx'
import TickerBar from './components/TickerBar.jsx'
import CardGrid from './components/CardGrid.jsx'
import AlertHistoryPanel, { useAlertHistory } from './components/AlertHistoryPanel.jsx'

export default function App() {
  const [layout, setLayout] = useState(null)
  const [themes, setThemes] = useState({})
  const [config, setConfig] = useState({})
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [alertPanelOpen, setAlertPanelOpen] = useState(false)
  const saveTimerRef = useRef(null)
  const layoutRef = useRef(null)

  const { events: alertEvents, unread: alertUnread, appendEvents, setPanelOpen, clearHistory } = useAlertHistory()

  // SSE connection for live card-data pushes + alert history updates
  const sseRef = useRef(null)
  const [sseData, setSseData] = useState({})  // card_type -> latest data

  useEffect(() => {
    Promise.all([fetchLayout(), fetchThemes(), fetchConfig()])
      .then(([lay, thms, cfg]) => {
        setLayout(lay)
        setThemes(thms)
        setConfig(cfg)
        setLastUpdated(new Date())
        layoutRef.current = lay
        const themeName = resolveTheme(lay)
        if (thms[themeName]) applyTheme(thms[themeName])
        setLoading(false)
      })
      .catch(err => {
        console.error('Failed to load app data:', err)
        setLoading(false)
      })
  }, [])

  // Auto-theme switcher
  useEffect(() => {
    if (!layout?.autoTheme) return
    const interval = setInterval(() => {
      const themeName = resolveTheme(layoutRef.current)
      if (themeName && themes[themeName]) {
        applyTheme(themes[themeName])
      }
    }, 60000)
    return () => clearInterval(interval)
  }, [layout?.autoTheme, themes])

  // SSE — connect once on mount, reconnect on disconnect
  useEffect(() => {
    let es = null
    let reconnectTimer = null

    function connect() {
      if (es) { es.close(); es = null }
      try {
        es = new EventSource('/api/events')
        sseRef.current = es

        es.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data)
            if (msg.type === 'card_update' && msg.card_type && msg.data) {
              setSseData(prev => ({ ...prev, [msg.card_type]: msg.data }))
            } else if (msg.type === 'alert_history_update' && msg.new_events) {
              // New alert events from backend — merge into local history
              appendEvents(msg.new_events)
            }
          } catch {}
        }

        es.onerror = () => {
          es?.close()
          reconnectTimer = setTimeout(connect, 5000)
        }
      } catch {}
    }

    connect()
    return () => {
      es?.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [appendEvents])

  // Dynamic favicon — updates color based on overall health
  useEffect(() => {
    async function syncFavicon() {
      try {
        const r = await fetch('/api/status-overview')
        if (!r.ok) return
        const d = await r.json()
        const { ok = 0, warn = 0, crit = 0, error = 0 } = d
        let color = '#00ff41'
        if (crit + error > 0) color = '#ff0000'
        else if (warn > 0) color = '#ffaa00'
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="${color}"/></svg>`
        let link = document.querySelector('link[rel="icon"]')
        if (!link) {
          link = document.createElement('link')
          link.rel = 'icon'
          link.type = 'image/svg+xml'
          document.head.appendChild(link)
        }
        link.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
      } catch {}
    }
    syncFavicon()
    const t = setInterval(syncFavicon, 30000)
    return () => clearInterval(t)
  }, [])

  // Also sync favicon when SSE pushes card updates (any state change)
  useEffect(() => {
    if (Object.keys(sseData).length === 0) return
    // Compute worst state from sseData
    let worst = 'ok'
    for (const d of Object.values(sseData)) {
      const st = d?.state
      if (st === 'crit' || st === 'critical' || st === 'error') { worst = 'crit'; break }
      if (st === 'warn' && worst !== 'crit') worst = 'warn'
    }
    const color = worst === 'crit' ? '#ff0000' : worst === 'warn' ? '#ffaa00' : '#00ff41'
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="14" fill="${color}"/></svg>`
    let link = document.querySelector('link[rel="icon"]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      link.type = 'image/svg+xml'
      document.head.appendChild(link)
    }
    link.href = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
  }, [sseData])

  const debouncedSave = useCallback((newLayout) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      saveLayout(newLayout).catch(err => console.error('Save layout failed:', err))
    }, 500)
  }, [])

  const handleLayoutChange = useCallback((newLayout) => {
    setLayout(newLayout)
    layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleThemeChange = useCallback((themeName) => {
    const newLayout = { ...layoutRef.current, theme: themeName }
    setLayout(newLayout)
    layoutRef.current = newLayout
    if (themes[themeName]) applyTheme(themes[themeName])
    debouncedSave(newLayout)
  }, [themes, debouncedSave])

  const handleAddCard = useCallback((cardType, cardTypeInfo) => {
    const cards = layoutRef.current?.cards || []
    const maxY = cards.reduce((m, c) => Math.max(m, (c.y || 0) + (c.h || 2)), 0)
    const newCard = {
      id: `${cardType}_${Date.now()}`,
      type: cardType,
      title: cardTypeInfo?.label || cardType,
      x: 0,
      y: maxY,
      w: 2,
      h: 3,
      config: { refresh_seconds: 60 },
    }
    const newLayout = { ...layoutRef.current, cards: [...cards, newCard] }
    setLayout(newLayout)
    layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleUpdateCard = useCallback((cardId, updates) => {
    const cards = (layoutRef.current?.cards || []).map(c =>
      c.id === cardId ? { ...c, ...updates } : c
    )
    const newLayout = { ...layoutRef.current, cards }
    setLayout(newLayout)
    layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  const handleRemoveCard = useCallback((cardId) => {
    const cards = (layoutRef.current?.cards || []).filter(c => c.id !== cardId)
    const newLayout = { ...layoutRef.current, cards }
    setLayout(newLayout)
    layoutRef.current = newLayout
    debouncedSave(newLayout)
  }, [debouncedSave])

  if (loading) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        gap: 16,
      }}>
        <span style={{
          fontSize: 13,
          color: 'var(--accent, #00ff41)',
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
        }}>
          Initializing NOC Dashboard...
        </span>
        <span style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.06em' }}>
          Connecting to ANTON
        </span>
      </div>
    )
  }

  return (
    <div
      className={editMode ? 'edit-mode' : ''}
      style={{ minHeight: '100vh', background: 'var(--background, #0a0a0a)' }}
    >
      <TopBar
        config={config}
        themes={themes}
        currentTheme={layout?.theme}
        onThemeChange={handleThemeChange}
        onAddCard={handleAddCard}
        lastUpdated={lastUpdated}
        editMode={editMode}
        onEditModeToggle={() => setEditMode(m => !m)}
        alertCount={alertUnread}
        onBellClick={() => {
          setAlertPanelOpen(o => !o)
          setPanelOpen(!alertPanelOpen)
        }}
      />
      <TickerBar />
      <CardGrid
        layout={layout}
        onLayoutChange={handleLayoutChange}
        onUpdateCard={handleUpdateCard}
        onRemoveCard={handleRemoveCard}
        editMode={editMode}
        sseData={sseData}
      />

      {/* Edit mode overlay banner */}
      {editMode && (
        <div style={{
          position: 'fixed',
          bottom: 16,
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(0,0,0,0.9)',
          border: '1px solid var(--accent, #00ff41)',
          borderRadius: 4,
          padding: '6px 20px',
          fontSize: 11,
          color: 'var(--accent, #00ff41)',
          letterSpacing: '0.1em',
          zIndex: 1000,
          pointerEvents: 'none',
        }}>
          EDIT MODE — Drag cards · Resize · Click ⚙ to configure · Click ✕ to remove
        </div>
      )}

      {/* Alert history slide-out panel */}
      <AlertHistoryPanel
        open={alertPanelOpen}
        onClose={() => {
          setAlertPanelOpen(false)
          setPanelOpen(false)
        }}
        events={alertEvents}
        unread={alertUnread}
        onClear={clearHistory}
      />
    </div>
  )
}
