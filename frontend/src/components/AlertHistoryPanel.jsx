import React, { useState, useEffect, useCallback } from 'react'

const ALERT_KEY = 'noc-alert-history'
const MAX_ALERTS = 100

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(ALERT_KEY) || '[]') } catch { return [] }
}
function saveHistory(h) {
  localStorage.setItem(ALERT_KEY, JSON.stringify(h))
}

export function useAlertHistory() {
  const [history, setHistory] = useState(loadHistory)

  const addAlerts = useCallback((alerts) => {
    if (!alerts || !alerts.length) return
    setHistory(prev => {
      const existing = new Set(prev.map(x => x.text))
      const ts = new Date().toISOString()
      const newEntries = alerts
        .filter(text => text && !existing.has(text))
        .map(text => ({ text, ts }))
      if (!newEntries.length) return prev
      const next = [...newEntries, ...prev].slice(0, MAX_ALERTS)
      saveHistory(next)
      return next
    })
  }, [])

  const clear = useCallback(() => {
    localStorage.removeItem(ALERT_KEY)
    setHistory([])
  }, [])

  return { history, addAlerts, clear }
}

export default function AlertHistoryPanel({ open, onClose, history, onClear }) {
  useEffect(() => {
    if (!open) return
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

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
      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: open ? 0 : -400,
        width: 380, height: '100vh',
        background: 'var(--card-background, #111)',
        borderLeft: '1px solid var(--card-border, #1e1e1e)',
        zIndex: 8001, display: 'flex', flexDirection: 'column',
        transition: 'right 0.3s ease',
        boxShadow: '-4px 0 20px rgba(0,0,0,0.5)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', borderBottom: '1px solid var(--card-border, #1e1e1e)',
          fontSize: 11, letterSpacing: '0.12em', color: 'var(--accent, #00ff41)',
          fontWeight: 700, flexShrink: 0,
        }}>
          <span>ALERT HISTORY</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              onClick={onClear}
              className="btn-ghost"
              style={{ fontSize: 10, padding: '2px 8px', letterSpacing: '0.06em' }}
            >CLEAR</button>
            <button
              onClick={onClose}
              className="btn-ghost"
              style={{ fontSize: 14, padding: '2px 8px' }}
            >&times;</button>
          </div>
        </div>
        {/* Feed */}
        <ul style={{
          listStyle: 'none', margin: 0, padding: 8,
          overflowY: 'auto', flex: 1,
        }}>
          {!history.length ? (
            <li style={{ color: 'var(--text-muted, #555)', fontSize: 12, textAlign: 'center', padding: '32px 16px' }}>
              No alert history recorded yet.
            </li>
          ) : history.map((item, i) => {
            const d = new Date(item.ts)
            const ts = d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            return (
              <li key={i} style={{
                display: 'flex', flexDirection: 'column', gap: 2,
                padding: '8px 10px',
                borderBottom: '1px solid var(--card-border, #1e1e1e)',
                fontSize: 12,
              }}>
                <span style={{ color: 'var(--text-muted, #555)', fontSize: 10, letterSpacing: '0.06em' }}>{ts}</span>
                <span style={{ color: 'var(--text-primary, #ccc)' }}>{item.text}</span>
              </li>
            )
          })}
        </ul>
      </div>
    </>
  )
}
