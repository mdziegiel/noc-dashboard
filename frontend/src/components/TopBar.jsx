import React, { useState } from 'react'
import AddCardPanel from './AddCardPanel.jsx'

const styles = {
  bar: {
    position: 'sticky',
    top: 0,
    zIndex: 100,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 16px',
    height: '52px',
    background: 'var(--card-background, #111)',
    borderBottom: '1px solid var(--card-border, #1e1e1e)',
    boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
  },
  left: { display: 'flex', flexDirection: 'column', gap: 1 },
  title: {
    fontSize: '15px',
    fontWeight: 700,
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    color: 'var(--accent, #00ff41)',
  },
  subtitle: {
    fontSize: '11px',
    color: 'var(--text-muted, #555)',
    letterSpacing: '0.05em',
  },
  right: { display: 'flex', alignItems: 'center', gap: 12 },
  updated: {
    fontSize: '11px',
    color: 'var(--text-muted, #555)',
  },
  themeBtn: {
    background: 'none',
    border: '1px solid var(--card-border, #1e1e1e)',
    color: 'var(--text-secondary, #a0a0a0)',
    padding: '4px 8px',
    fontSize: '11px',
    cursor: 'pointer',
    borderRadius: '3px',
    letterSpacing: '0.04em',
    fontFamily: 'inherit',
  },
  addBtn: {
    background: 'var(--accent, #00ff41)',
    border: 'none',
    color: '#000',
    width: 28,
    height: 28,
    fontSize: '18px',
    lineHeight: '28px',
    textAlign: 'center',
    cursor: 'pointer',
    borderRadius: '50%',
    fontWeight: 'bold',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
}

export default function TopBar({ config, themes, currentTheme, onThemeChange, onAddCard, lastUpdated }) {
  const [showAdd, setShowAdd] = useState(false)
  const themeNames = Object.keys(themes || {})

  function cycleTheme() {
    if (!themeNames.length) return
    const idx = themeNames.indexOf(currentTheme)
    const next = themeNames[(idx + 1) % themeNames.length]
    onThemeChange(next)
  }

  function formatTime(d) {
    if (!d) return ''
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  return (
    <>
      <div style={styles.bar}>
        <div style={styles.left}>
          <span style={styles.title}>{config?.title || 'NOC Dashboard'}</span>
          {config?.subtitle && <span style={styles.subtitle}>{config.subtitle}</span>}
        </div>
        <div style={styles.right}>
          {lastUpdated && (
            <span style={styles.updated}>Updated {formatTime(lastUpdated)}</span>
          )}
          {themeNames.length > 0 && (
            <button style={styles.themeBtn} onClick={cycleTheme} title="Switch theme">
              ◐ {currentTheme || 'theme'}
            </button>
          )}
          <button style={styles.addBtn} onClick={() => setShowAdd(true)} title="Add card">
            +
          </button>
        </div>
      </div>
      {showAdd && (
        <AddCardPanel
          onAdd={(type, info) => { onAddCard(type, info); setShowAdd(false) }}
          onClose={() => setShowAdd(false)}
        />
      )}
    </>
  )
}
