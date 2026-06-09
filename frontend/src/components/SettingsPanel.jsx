import React, { useState } from 'react'

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    zIndex: 300,
    display: 'flex',
    justifyContent: 'flex-end',
  },
  backdrop: {
    position: 'absolute',
    inset: 0,
    background: 'rgba(0,0,0,0.4)',
  },
  panel: {
    position: 'relative',
    zIndex: 1,
    width: 320,
    height: '100vh',
    background: 'var(--card-background, #111)',
    borderLeft: '1px solid var(--card-border, #1e1e1e)',
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    animation: 'slideIn 0.15s ease',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 16px',
    borderBottom: '1px solid var(--card-border, #1e1e1e)',
    position: 'sticky',
    top: 0,
    background: 'var(--card-background, #111)',
    zIndex: 1,
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
  body: { padding: 16, display: 'flex', flexDirection: 'column', gap: 14, flex: 1 },
  label: {
    display: 'block',
    fontSize: '11px',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: 'var(--text-muted, #555)',
    marginBottom: 4,
  },
  input: {
    width: '100%',
    background: 'var(--background, #0a0a0a)',
    border: '1px solid var(--card-border, #1e1e1e)',
    color: 'var(--text-primary, #e0e0e0)',
    padding: '6px 8px',
    fontSize: '12px',
    borderRadius: '3px',
    fontFamily: 'inherit',
    outline: 'none',
  },
  select: {
    width: '100%',
    background: 'var(--background, #0a0a0a)',
    border: '1px solid var(--card-border, #1e1e1e)',
    color: 'var(--text-primary, #e0e0e0)',
    padding: '6px 8px',
    fontSize: '12px',
    borderRadius: '3px',
    fontFamily: 'inherit',
    outline: 'none',
  },
  toggleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  toggle: {
    cursor: 'pointer',
    fontSize: '11px',
    color: 'var(--text-secondary, #a0a0a0)',
    background: 'var(--background, #0a0a0a)',
    border: '1px solid var(--card-border, #1e1e1e)',
    padding: '3px 10px',
    borderRadius: '3px',
    fontFamily: 'inherit',
  },
  textarea: {
    width: '100%',
    background: 'var(--background, #0a0a0a)',
    border: '1px solid var(--card-border, #1e1e1e)',
    color: 'var(--text-primary, #e0e0e0)',
    padding: '6px 8px',
    fontSize: '11px',
    borderRadius: '3px',
    fontFamily: 'inherit',
    outline: 'none',
    resize: 'vertical',
    minHeight: 80,
  },
  footer: {
    padding: 16,
    borderTop: '1px solid var(--card-border, #1e1e1e)',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  saveBtn: {
    background: 'var(--accent, #00ff41)',
    border: 'none',
    color: '#000',
    padding: '8px',
    fontSize: '12px',
    cursor: 'pointer',
    borderRadius: '3px',
    fontFamily: 'inherit',
    fontWeight: 700,
    letterSpacing: '0.05em',
  },
  removeBtn: {
    background: 'none',
    border: '1px solid var(--error-color, #ff3333)',
    color: 'var(--error-color, #ff3333)',
    padding: '7px',
    fontSize: '12px',
    cursor: 'pointer',
    borderRadius: '3px',
    fontFamily: 'inherit',
    letterSpacing: '0.04em',
  },
  removeBtnConfirm: {
    background: 'var(--error-color, #ff3333)',
    border: '1px solid var(--error-color, #ff3333)',
    color: '#fff',
    padding: '7px',
    fontSize: '12px',
    cursor: 'pointer',
    borderRadius: '3px',
    fontFamily: 'inherit',
    letterSpacing: '0.04em',
  },
}

export default function SettingsPanel({ card, onSave, onRemove, onClose }) {
  const [title, setTitle] = useState(card.title || '')
  const [graph, setGraph] = useState(card.config?.graph ?? true)
  const [graphType, setGraphType] = useState(card.config?.graph_type || 'sparkline')
  const [graphColor, setGraphColor] = useState(card.config?.graph_color || '')
  const [refresh, setRefresh] = useState(card.config?.refresh_seconds || 60)
  const [thresholds, setThresholds] = useState(
    card.config?.thresholds ? JSON.stringify(card.config.thresholds, null, 2) : ''
  )
  const [confirmRemove, setConfirmRemove] = useState(false)

  function handleSave() {
    let parsedThresholds = undefined
    if (thresholds.trim()) {
      try { parsedThresholds = JSON.parse(thresholds) } catch { /* ignore */ }
    }
    onSave({
      title,
      config: {
        ...card.config,
        graph,
        graph_type: graphType,
        graph_color: graphColor || undefined,
        refresh_seconds: Number(refresh),
        thresholds: parsedThresholds,
      },
    })
    onClose()
  }

  function handleRemove() {
    if (!confirmRemove) { setConfirmRemove(true); return }
    onRemove(card.id)
    onClose()
  }

  return (
    <div style={styles.overlay}>
      <div style={styles.backdrop} onClick={onClose} />
      <div style={styles.panel}>
        <div style={styles.header}>
          <span style={styles.title}>Card Settings</span>
          <button style={styles.closeBtn} onClick={onClose}>✕</button>
        </div>
        <div style={styles.body}>
          <div>
            <label style={styles.label}>Title</label>
            <input style={styles.input} value={title} onChange={e => setTitle(e.target.value)} />
          </div>
          <div>
            <div style={styles.toggleRow}>
              <label style={styles.label}>Graph</label>
              <button
                style={styles.toggle}
                onClick={() => setGraph(g => !g)}
              >
                {graph ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>
          <div>
            <label style={styles.label}>Graph Type</label>
            <select style={styles.select} value={graphType} onChange={e => setGraphType(e.target.value)}>
              <option value="sparkline">Sparkline</option>
              <option value="area">Area</option>
              <option value="gauge">Gauge</option>
              <option value="donut">Donut</option>
            </select>
          </div>
          <div>
            <label style={styles.label}>Graph Color</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="color"
                value={graphColor || '#00ff41'}
                onChange={e => setGraphColor(e.target.value)}
                style={{ width: 32, height: 28, border: 'none', background: 'none', cursor: 'pointer' }}
              />
              <input
                style={{ ...styles.input, flex: 1 }}
                value={graphColor}
                onChange={e => setGraphColor(e.target.value)}
                placeholder="var(--graph-line-color)"
              />
            </div>
          </div>
          <div>
            <label style={styles.label}>Refresh (seconds)</label>
            <input
              style={styles.input}
              type="number"
              min="10"
              value={refresh}
              onChange={e => setRefresh(e.target.value)}
            />
          </div>
          <div>
            <label style={styles.label}>Thresholds (JSON)</label>
            <textarea
              style={styles.textarea}
              value={thresholds}
              onChange={e => setThresholds(e.target.value)}
              placeholder='{"warn": 80, "crit": 90}'
            />
          </div>
        </div>
        <div style={styles.footer}>
          <button style={styles.saveBtn} onClick={handleSave}>Save Changes</button>
          <button
            style={confirmRemove ? styles.removeBtnConfirm : styles.removeBtn}
            onClick={handleRemove}
          >
            {confirmRemove ? 'Confirm Remove?' : 'Remove Card'}
          </button>
        </div>
      </div>
    </div>
  )
}
