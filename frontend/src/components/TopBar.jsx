import React, { useState, useEffect } from 'react'
import AddCardPanel from './AddCardPanel.jsx'

const REFRESH_INTERVAL = 30_000  // 30s status overview refresh

async function fetchStatusOverview() {
  try {
    const r = await fetch('/api/status-overview')
    if (!r.ok) return null
    return r.json()
  } catch {
    return null
  }
}

function StatusOverview({ overview }) {
  if (!overview) return null
  const { ok = 0, warn = 0, crit = 0, error = 0 } = overview
  const total = ok + warn + crit + error

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      fontSize: 11,
      letterSpacing: '0.04em',
    }}>
      {ok > 0 && (
        <span style={{ color: 'var(--ok-color, #00ff41)', display: 'flex', alignItems: 'center', gap: 3 }}>
          <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--ok-color, #00ff41)' }} />
          {ok} OK
        </span>
      )}
      {warn > 0 && (
        <span style={{ color: 'var(--warn-color, #ffaa00)', display: 'flex', alignItems: 'center', gap: 3 }}>
          <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--warn-color, #ffaa00)' }} />
          {warn} Warn
        </span>
      )}
      {(crit + error) > 0 && (
        <span style={{ color: 'var(--critical-color, #ff0000)', display: 'flex', alignItems: 'center', gap: 3, animation: 'blink 1.2s infinite' }}>
          <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--critical-color, #ff0000)' }} />
          {crit + error} Crit
        </span>
      )}
      {total === 0 && (
        <span style={{ color: 'var(--text-muted, #555)' }}>—</span>
      )}
    </div>
  )
}

export default function TopBar({ config, themes, currentTheme, onThemeChange, onAddCard, lastUpdated, editMode, onEditModeToggle, alertCount, onBellClick, onSettingsClick, authUser }) {
  const [showAdd, setShowAdd] = useState(false)
  const [overview, setOverview] = useState(null)
  const [gearOpen, setGearOpen] = useState(false)
  const themeNames = Object.keys(themes || {})

  useEffect(() => {
    let mounted = true
    async function load() {
      const d = await fetchStatusOverview()
      if (mounted && d) setOverview(d)
    }
    load()
    const t = setInterval(load, REFRESH_INTERVAL)
    return () => { mounted = false; clearInterval(t) }
  }, [])

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

  const barStyle = {
    position: 'sticky',
    top: 0,
    zIndex: 100,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 16px',
    height: 52,
    background: 'var(--top-bar-background, #000)',
    borderBottom: '1px solid var(--top-bar-border, #1a1a1a)',
    boxShadow: '0 2px 12px rgba(0,0,0,0.6)',
    flexShrink: 0,
  }

  return (
    <>
      <div style={barStyle}>
        {/* Left: title + subtitle + status overview */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <span style={{
              fontSize: 15,
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--accent, #00ff41)',
              textShadow: '0 0 12px rgba(0,255,65,0.4)',
            }}>
              {config?.title || 'NOC Dashboard'}
            </span>
            {config?.subtitle && (
              <span style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em' }}>
                {config.subtitle}
              </span>
            )}
          </div>
          <div style={{ width: 1, height: 28, background: 'var(--top-bar-border, #1a1a1a)' }} />
          <StatusOverview overview={overview} />
        </div>

        {/* Right: updated time, edit mode, theme, add */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Bell / alert history */}
          <button
            className="btn-ghost"
            onClick={onBellClick}
            title="Alert history"
            style={{ fontSize: 14, padding: '3px 8px', position: 'relative' }}
          >
            &#128276;
            {alertCount > 0 && (
              <span style={{
                position: 'absolute', top: -4, right: -4,
                background: 'var(--critical-color, #ff0000)',
                color: '#fff', borderRadius: '50%', fontSize: 9,
                width: 14, height: 14, display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                fontWeight: 700,
              }}>
                {alertCount > 9 ? '9+' : alertCount}
              </span>
            )}
          </button>

          {lastUpdated && (
            <span style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.04em' }}>
              {formatTime(lastUpdated)}
            </span>
          )}

          {/* Gear menu: edit + settings */}
          <div style={{ position: 'relative' }}>
            <button
              className="btn-ghost"
              onClick={() => setGearOpen(o => !o)}
              style={{
                borderColor: editMode ? 'var(--accent, #00ff41)' : undefined,
                color: editMode ? 'var(--accent, #00ff41)' : undefined,
                fontSize: 10,
                padding: '3px 8px',
                letterSpacing: '0.06em',
              }}
              title="Dashboard menu"
            >
              ⚙▾
            </button>
            {gearOpen && (
              <div className="user-dropdown gear-dropdown">
                <div className="user-dropdown-id" aria-label="Signed in user">
                  <b>{authUser?.username || 'admin'}</b>
                  <span>{authUser?.role || 'Administrator'}</span>
                </div>
                <div className="user-dropdown-divider" />
                <button onClick={() => { setGearOpen(false); fetch('/api/logout', { method: 'POST' }).finally(() => { window.location.href = '/login' }) }}>Logout</button>
                <button onClick={() => { onEditModeToggle?.(); setGearOpen(false) }}>{editMode ? 'Done Editing' : 'Edit Dashboard'}</button>
                <button onClick={() => { onSettingsClick?.(); setGearOpen(false) }}>Settings</button>
              </div>
            )}
          </div>

          {/* Theme cycle */}
          {themeNames.length > 0 && (
            <button
              className="btn-ghost"
              onClick={cycleTheme}
              title="Switch theme"
              style={{ fontSize: 10, padding: '3px 8px', letterSpacing: '0.06em' }}
            >
              ◐ {(currentTheme || 'theme').toUpperCase().replace(/-/g, ' ')}
            </button>
          )}

          {/* Add card — only in edit mode */}
          {editMode && (
            <button
              style={{
                background: 'var(--accent, #00ff41)',
                border: 'none',
                color: '#000',
                width: 26,
                height: 26,
                fontSize: 16,
                lineHeight: '26px',
                textAlign: 'center',
                cursor: 'pointer',
                borderRadius: '50%',
                fontWeight: 'bold',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
              onClick={() => setShowAdd(true)}
              title="Add card"
            >
              +
            </button>
          )}
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
