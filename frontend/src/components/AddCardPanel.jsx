import React, { useState, useEffect } from 'react'
import { fetchCardTypes } from '../api.js'

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    zIndex: 200,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'center',
    paddingTop: 60,
  },
  panel: {
    background: 'var(--card-background, #111)',
    border: '1px solid var(--card-border, #1e1e1e)',
    borderRadius: '4px',
    width: '680px',
    maxHeight: '70vh',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    borderBottom: '1px solid var(--card-border, #1e1e1e)',
  },
  title: {
    fontSize: '12px',
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    color: 'var(--accent, #00ff41)',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted, #555)',
    cursor: 'pointer',
    fontSize: '16px',
    fontFamily: 'inherit',
  },
  searchWrap: {
    padding: '10px 16px',
    borderBottom: '1px solid var(--card-border, #1e1e1e)',
  },
  search: {
    width: '100%',
    background: 'var(--background, #0a0a0a)',
    border: '1px solid var(--card-border, #1e1e1e)',
    color: 'var(--text-primary, #e0e0e0)',
    padding: '6px 10px',
    fontSize: '12px',
    borderRadius: '3px',
    fontFamily: 'inherit',
    outline: 'none',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 10,
    padding: 16,
    overflowY: 'auto',
  },
  card: {
    background: 'var(--background, #0a0a0a)',
    border: '1px solid var(--card-border, #1e1e1e)',
    borderRadius: '3px',
    padding: '10px',
    cursor: 'pointer',
    transition: 'border-color 0.15s',
  },
  cardLabel: {
    fontSize: '12px',
    fontWeight: 700,
    color: 'var(--accent, #00ff41)',
    marginBottom: 4,
    letterSpacing: '0.04em',
  },
  cardDesc: {
    fontSize: '11px',
    color: 'var(--text-muted, #555)',
    lineHeight: 1.4,
  },
}

export default function AddCardPanel({ onAdd, onClose }) {
  const [cardTypes, setCardTypes] = useState({})
  const [search, setSearch] = useState('')

  useEffect(() => {
    fetchCardTypes().then(setCardTypes).catch(console.error)
  }, [])

  const filtered = Object.entries(cardTypes).filter(([type, info]) => {
    if (!search) return true
    const q = search.toLowerCase()
    return type.toLowerCase().includes(q) || (info.label || '').toLowerCase().includes(q)
  })

  return (
    <div style={styles.overlay} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={styles.panel}>
        <div style={styles.header}>
          <span style={styles.title}>Add Card</span>
          <button style={styles.closeBtn} onClick={onClose}>✕</button>
        </div>
        <div style={styles.searchWrap}>
          <input
            style={styles.search}
            placeholder="Search card types..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
          />
        </div>
        <div style={styles.grid}>
          {filtered.map(([type, info]) => (
            <div
              key={type}
              style={styles.card}
              onClick={() => onAdd(type, info)}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent, #00ff41)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--card-border, #1e1e1e)'}
            >
              <div style={styles.cardLabel}>{info.label || type}</div>
              <div style={styles.cardDesc}>{info.description || ''}</div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ gridColumn: '1/-1', color: 'var(--text-muted, #555)', fontSize: 12, padding: 8 }}>
              No card types found.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
