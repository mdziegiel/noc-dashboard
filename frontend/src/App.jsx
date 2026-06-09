import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fetchLayout, fetchThemes, fetchConfig, saveLayout } from './api.js'
import { applyTheme, resolveTheme } from './theme.js'
import TopBar from './components/TopBar.jsx'
import CardGrid from './components/CardGrid.jsx'

export default function App() {
  const [layout, setLayout] = useState(null)
  const [themes, setThemes] = useState({})
  const [config, setConfig] = useState({})
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading] = useState(true)
  const saveTimerRef = useRef(null)
  const layoutRef = useRef(null)

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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--accent, #00ff41)' }}>
        Loading NOC Dashboard...
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--background, #0a0a0a)' }}>
      <TopBar
        config={config}
        themes={themes}
        currentTheme={layout?.theme}
        onThemeChange={handleThemeChange}
        onAddCard={handleAddCard}
        lastUpdated={lastUpdated}
      />
      <CardGrid
        layout={layout}
        onLayoutChange={handleLayoutChange}
        onUpdateCard={handleUpdateCard}
        onRemoveCard={handleRemoveCard}
      />
    </div>
  )
}
