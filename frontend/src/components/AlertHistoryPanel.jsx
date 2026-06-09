import React, { useState, useEffect, useCallback, useRef } from 'react'

const MAX_LOCAL = 500

// Level -> color mapping
const LEVEL_COLOR = {
  crit:  'var(--critical-color, #ff0000)',
  error: 'var(--error-color, #ff3333)',
  warn:  'var(--warn-color, #ffaa00)',
  ok:    'var(--ok-color, #00ff41)',
  info:  'var(--text-secondary, #a0a0a0)',
}

// Level -> label
const LEVEL_LABEL = {
  crit:  'CRIT',
  error: 'ERR',
  warn:  'WARN',
  ok:    'OK',
  info:  'INFO',
}

function levelColor(level) {
  return LEVEL_COLOR[level] || LEVEL_COLOR.info
}

function levelLabel(level) {
  return LEVEL_LABEL[level] || level?.toUpperCase() || 'INFO'
}

function formatTs(tsStr) {
  if (!tsStr) return ''
  const d = new Date(tsStr)
  if (isNaN(d.getTime())) return tsStr
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDate(tsStr) {
  if (!tsStr) return ''
  const d = new Date(tsStr)
  if (isNaN(d.getTime())) return ''
  const today = new Date()
  if (d.toDateString() === today.toDateString()) return 'Today'
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

// ── Hook — loads from backend, merges SSE pushes ─────────────────────────────

export function useAlertHistory() {
  const [events, setEvents] = useState([])
  const [unread, setUnread] = useState(0)
  const panelOpenRef = useRef(false)
  const loadedRef = useRef(false)

  // Initial load from backend
  useEffect(() => {
    fetch('/api/alert-history')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d?.events) {
          setEvents(d.events.slice(0, MAX_LOCAL))
          loadedRef.current = true
        }
      })
      .catch(() => {})
  }, [])

  // Called from App.jsx SSE handler when alert_history_update arrives
  const appendEvents = useCallback((newEvents) => {
    if (!newEvents || !newEvents.length) return
    setEvents(prev => {
      const merged = [...newEvents, ...prev].slice(0, MAX_LOCAL)
      return merged
    })
    if (!panelOpenRef.current) {
      setUnread(prev => prev + newEvents.length)
    }
  }, [])

  const markRead = useCallback(() => {
    setUnread(0)
    panelOpenRef.current = true
  }, [])

  const setPanelOpen = useCallback((open) => {
    panelOpenRef.current = open
    if (open) setUnread(0)
  }, [])

  const clearHistory = useCallback(() => {
    fetch('/api/alert-history/clear', { method: 'POST' }).catch(() => {})
    setEvents([])
    setUnread(0)
  }, [])

  return { events, unread, appendEvents, markRead, setPanelOpen, clearHistory }
}


// ── Alert History Panel component ────────────────────────────────────────────

export default function AlertHistoryPanel({ open, onClose, events, unread, onClear }) {
  const [filter, setFilter] = useState('all')  // all | crit | warn | ok

  useEffect(() => {
    if (!open) return
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const filtered = filter === 'all'
    ? events
    : events.filter(e => e.level === filter || (filter === 'crit' && e.level === 'error'))

  // Group by date for display
  const groups = []
  let lastDate = null
  for (const ev of filtered) {
    const d = formatDate(ev.ts)
    if (d !== lastDate) {
      groups.push({ type: 'date', label: d })
      lastDate = d
    }
    groups.push({ type: 'event', ev })
  }

  const critCount = events.filter(e => e.level === 'crit' || e.level === 'error').length
  const warnCount = events.filter(e => e.level === 'warn').length

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          onClick={onClose}
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.4)', zIndex: 8000,
          }}
        />
      )}

      {/* Slide-out panel */}
      <div style={{
        position: 'fixed', top: 0, right: open ? 0 : -420,
        width: 400, height: '100vh',
        background: 'var(--card-background, #111)',
        borderLeft: '1px solid var(--card-border, #1e1e1e)',
        zIndex: 8001, display: 'flex', flexDirection: 'column',
        transition: 'right 0.28s cubic-bezier(0.4,0,0.2,1)',
        boxShadow: '-6px 0 24px rgba(0,0,0,0.6)',
      }}>

        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px',
          borderBottom: '1px solid var(--card-border, #1e1e1e)',
          flexShrink: 0,
          background: 'var(--top-bar-background, #000)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              fontSize: 11, fontWeight: 700, letterSpacing: '0.12em',
              color: 'var(--accent, #00ff41)', textTransform: 'uppercase',
            }}>
              SOC Event Feed
            </span>
            {/* Mini stats */}
            {critCount > 0 && (
              <span style={{
                fontSize: 10, padding: '1px 6px', borderRadius: 3,
                background: 'rgba(255,0,0,0.12)',
                color: 'var(--critical-color, #ff0000)',
                fontWeight: 700, letterSpacing: '0.04em',
              }}>
                {critCount} CRIT
              </span>
            )}
            {warnCount > 0 && (
              <span style={{
                fontSize: 10, padding: '1px 6px', borderRadius: 3,
                background: 'rgba(255,170,0,0.12)',
                color: 'var(--warn-color, #ffaa00)',
                fontWeight: 700, letterSpacing: '0.04em',
              }}>
                {warnCount} WARN
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button
              onClick={onClear}
              className="btn-ghost"
              style={{ fontSize: 10, padding: '2px 8px', letterSpacing: '0.06em', opacity: 0.7 }}
            >
              CLEAR
            </button>
            <button
              onClick={onClose}
              className="btn-ghost"
              style={{ fontSize: 14, padding: '2px 8px', lineHeight: 1 }}
            >
              &times;
            </button>
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{
          display: 'flex', gap: 0,
          borderBottom: '1px solid var(--card-border, #1e1e1e)',
          flexShrink: 0,
        }}>
          {[
            { key: 'all',  label: `ALL (${events.length})` },
            { key: 'crit', label: `CRIT (${critCount})` },
            { key: 'warn', label: `WARN (${warnCount})` },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              style={{
                flex: 1, padding: '6px 4px', border: 'none',
                background: filter === tab.key ? 'rgba(0,255,65,0.06)' : 'transparent',
                color: filter === tab.key ? 'var(--accent, #00ff41)' : 'var(--text-muted, #555)',
                fontSize: 10, letterSpacing: '0.08em', cursor: 'pointer',
                borderBottom: filter === tab.key ? '1px solid var(--accent, #00ff41)' : '1px solid transparent',
                fontFamily: 'inherit',
                transition: 'color 0.15s',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Event feed */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '4px 0',
        }}>
          {filtered.length === 0 ? (
            <div style={{
              padding: '40px 20px', textAlign: 'center',
              color: 'var(--text-muted, #555)', fontSize: 12,
              letterSpacing: '0.04em',
            }}>
              {events.length === 0 ? 'No events recorded yet.' : 'No events match this filter.'}
            </div>
          ) : groups.map((item, i) => {
            if (item.type === 'date') {
              return (
                <div key={`date-${i}`} style={{
                  padding: '8px 14px 4px',
                  fontSize: 10, letterSpacing: '0.1em',
                  color: 'var(--text-muted, #444)',
                  textTransform: 'uppercase',
                  borderTop: i > 0 ? '1px solid var(--card-border, #1e1e1e)' : 'none',
                }}>
                  {item.label}
                </div>
              )
            }

            const ev = item.ev
            const color = levelColor(ev.level)
            const lbl = levelLabel(ev.level)
            const ts = formatTs(ev.ts)

            return (
              <div
                key={`ev-${i}`}
                style={{
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                  padding: '7px 14px',
                  borderBottom: '1px solid rgba(255,255,255,0.03)',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                {/* Severity badge */}
                <span style={{
                  flexShrink: 0, marginTop: 1,
                  fontSize: 9, fontWeight: 700, letterSpacing: '0.06em',
                  padding: '2px 5px', borderRadius: 2,
                  background: `${color}18`,
                  color: color,
                  minWidth: 32, textAlign: 'center',
                  fontFamily: 'inherit',
                }}>
                  {lbl}
                </span>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 12, color: 'var(--text-primary, #e0e0e0)',
                    lineHeight: 1.4, wordBreak: 'break-word',
                  }}>
                    {ev.text}
                  </div>
                  <div style={{
                    fontSize: 10, color: 'var(--text-muted, #555)',
                    marginTop: 2, display: 'flex', gap: 8,
                  }}>
                    <span>{ts}</span>
                    {ev.card_type && (
                      <span style={{ opacity: 0.7 }}>
                        {ev.card_type.replace(/_/g, '-')}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div style={{
          padding: '6px 14px', borderTop: '1px solid var(--card-border, #1e1e1e)',
          fontSize: 10, color: 'var(--text-muted, #555)',
          flexShrink: 0, letterSpacing: '0.04em',
        }}>
          {events.length} event{events.length !== 1 ? 's' : ''} — persisted to state/alert_history.json
        </div>
      </div>
    </>
  )
}
