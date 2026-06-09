import React, { useState } from 'react'

const AVAILABLE_ICONS = [
  'Server', 'HardDrive', 'Box', 'Archive', 'RotateCcw', 'Home', 'Activity',
  'Shield', 'AlertTriangle', 'ShieldAlert', 'Cloud', 'Eye',
  'Wifi', 'Network', 'Globe', 'Filter',
  'Database',
  'Play', 'BarChart2', 'Film', 'Search', 'Download', 'List',
  'HeartPulse', 'ExternalLink', 'Tv',
]

const ICON_PATHS = {
  Server:       'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z',
  HardDrive:    'M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 17.76 4H6.24a2 2 0 0 0-1.79 1.11zM6 16h.01M10 16h.01',
  Box:          'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z',
  Archive:      'M21 8v13H3V8M1 3h22v5H1zM10 12h4',
  RotateCcw:    'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5',
  Home:         'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 22V12h6v10',
  Activity:     'M22 12h-4l-3 9L9 3l-3 9H2',
  Shield:       'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  AlertTriangle:'M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0zM12 9v4M12 17h.01',
  ShieldAlert:  'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10zM12 8v4M12 16h.01',
  Cloud:        'M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z',
  Eye:          'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  Wifi:         'M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01',
  Network:      'M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 0-2-2V9m0 0h18',
  Globe:        'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z',
  Filter:       'M22 3H2l8 9.46V19l4 2v-8.54L22 3z',
  Database:     'M12 2C6.48 2 2 4.69 2 8s4.48 6 10 6 10-2.69 10-6-4.48-6-10-6zM2 8v4c0 3.31 4.48 6 10 6s10-2.69 10-6V8M2 12v4c0 3.31 4.48 6 10 6s10-2.69 10-6v-4',
  Play:         'M5 3l14 9-14 9V3z',
  BarChart2:    'M18 20V10M12 20V4M6 20v-6',
  Film:         'M19.82 2H4.18A2.18 2.18 0 0 0 2 4.18v15.64A2.18 2.18 0 0 0 4.18 22h15.64A2.18 2.18 0 0 0 22 19.82V4.18A2.18 2.18 0 0 0 19.82 2zM7 2v20M17 2v20M2 12h20',
  Search:       'M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM21 21l-4.35-4.35',
  Download:     'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  List:         'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  HeartPulse:   'M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7z',
  ExternalLink: 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3',
  Tv:           'M2 7h20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zM8 21h8M12 17v4',
}

function Icon({ name, size = 14, color = 'currentColor' }) {
  const path = ICON_PATHS[name]
  if (!path) return null
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {path.split('M').filter(Boolean).map((seg, i) => (
        <path key={i} d={'M' + seg} />
      ))}
    </svg>
  )
}

const fieldStyle = { marginBottom: 14 }
const labelStyle = {
  display: 'block',
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color: 'var(--muted)',
  marginBottom: 4,
}

export default function SettingsPanel({ card, onSave, onRemove, onClose }) {
  const [title, setTitle]             = useState(card.title || '')
  const [icon, setIcon]               = useState(card.config?.icon || '')
  const [graph, setGraph]             = useState(card.config?.graph ?? true)
  const [graphType, setGraphType]     = useState(card.config?.graph_type || 'sparkline')
  const [graphColor, setGraphColor]   = useState(card.config?.graph_color || '')
  const [refresh, setRefresh]         = useState(card.config?.refresh_seconds || 60)
  const [thresholds, setThresholds]   = useState(
    card.config?.thresholds ? JSON.stringify(card.config.thresholds, null, 2) : ''
  )
  const [notes, setNotes]             = useState(card.config?.notes || '')
  const [showIconPicker, setShowIconPicker] = useState(false)
  const [confirmRemove, setConfirmRemove]   = useState(false)

  function handleSave() {
    let parsedThresholds = undefined
    if (thresholds.trim()) {
      try { parsedThresholds = JSON.parse(thresholds) } catch {}
    }
    onSave({
      title,
      config: {
        ...card.config,
        icon: icon || undefined,
        graph,
        graph_type: graphType,
        graph_color: graphColor || undefined,
        refresh_seconds: Number(refresh),
        thresholds: parsedThresholds,
        notes: notes || undefined,
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
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 300,
      display: 'flex',
      justifyContent: 'flex-end',
    }}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(0,0,0,0.45)',
        }}
        onClick={onClose}
      />
      <div style={{
        position: 'relative',
        zIndex: 1,
        width: 320,
        height: '100vh',
        background: 'var(--panel)',
        borderLeft: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto',
        animation: 'slideIn 0.15s ease',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid var(--line)',
          position: 'sticky',
          top: 0,
          background: 'var(--panel)',
          zIndex: 1,
        }}>
          <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--green)' }}>
            Card Settings
          </span>
          <button
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 16, fontFamily: 'inherit' }}
            onClick={onClose}
          >✕</button>
        </div>

        {/* Body */}
        <div style={{ padding: 16, flex: 1, display: 'flex', flexDirection: 'column', gap: 0 }}>

          {/* Type label (read-only) */}
          <div style={fieldStyle}>
            <label style={labelStyle}>Card Type</label>
            <div style={{ fontSize: 11, color: 'var(--muted)', letterSpacing: '0.04em' }}>
              {card.type}
            </div>
          </div>

          {/* Title */}
          <div style={fieldStyle}>
            <label style={labelStyle}>Title</label>
            <input className="noc-input" value={title} onChange={e => setTitle(e.target.value)} />
          </div>

          {/* Icon picker */}
          <div style={fieldStyle}>
            <label style={labelStyle}>Icon</label>
            <button
              className="btn-ghost"
              style={{ width: '100%', textAlign: 'left', display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px' }}
              onClick={() => setShowIconPicker(p => !p)}
            >
              {icon ? <Icon name={icon} size={14} color="var(--green)" /> : '—'}
              <span style={{ fontSize: 11, flex: 1 }}>{icon || 'Auto (default)'}</span>
              <span style={{ fontSize: 10, color: 'var(--muted)' }}>{showIconPicker ? '▲' : '▼'}</span>
            </button>
            {showIconPicker && (
              <div style={{
                marginTop: 6,
                border: '1px solid var(--line)',
                borderRadius: 3,
                padding: 8,
                background: 'var(--bg)',
                display: 'grid',
                gridTemplateColumns: 'repeat(5, 1fr)',
                gap: 4,
              }}>
                {/* Clear option */}
                <button
                  className="btn-ghost"
                  style={{ padding: '4px', display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.5 }}
                  onClick={() => { setIcon(''); setShowIconPicker(false) }}
                  title="Auto (default)"
                >
                  <span style={{ fontSize: 9 }}>AUTO</span>
                </button>
                {AVAILABLE_ICONS.map(ic => (
                  <button
                    key={ic}
                    title={ic}
                    className="btn-ghost"
                    style={{
                      padding: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      borderColor: icon === ic ? 'var(--green)' : undefined,
                    }}
                    onClick={() => { setIcon(ic); setShowIconPicker(false) }}
                  >
                    <Icon name={ic} size={13} color={icon === ic ? 'var(--green)' : 'var(--muted)'} />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Graph toggle */}
          <div style={fieldStyle}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <label style={labelStyle}>Graph</label>
              <button
                className="btn-ghost"
                style={{
                  fontSize: 10,
                  padding: '2px 8px',
                  borderColor: graph ? 'var(--green)' : undefined,
                  color: graph ? 'var(--green)' : undefined,
                }}
                onClick={() => setGraph(g => !g)}
              >
                {graph ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>

          {graph && (
            <>
              <div style={fieldStyle}>
                <label style={labelStyle}>Graph Type</label>
                <select className="noc-select" value={graphType} onChange={e => setGraphType(e.target.value)}>
                  <option value="sparkline">Sparkline</option>
                  <option value="area">Area</option>
                  <option value="gauge">Gauge</option>
                  <option value="donut">Donut</option>
                </select>
              </div>
              <div style={fieldStyle}>
                <label style={labelStyle}>Graph Color</label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="color"
                    value={graphColor || '#00ff41'}
                    onChange={e => setGraphColor(e.target.value)}
                    style={{ width: 32, height: 28, border: 'none', background: 'none', cursor: 'pointer', flexShrink: 0 }}
                  />
                  <input
                    className="noc-input"
                    style={{ flex: 1 }}
                    value={graphColor}
                    onChange={e => setGraphColor(e.target.value)}
                    placeholder="var(--green)"
                  />
                </div>
              </div>
            </>
          )}

          {/* Refresh */}
          <div style={fieldStyle}>
            <label style={labelStyle}>Refresh Interval (seconds)</label>
            <input
              className="noc-input"
              type="number"
              min="10"
              value={refresh}
              onChange={e => setRefresh(e.target.value)}
            />
          </div>

          {/* Thresholds */}
          <div style={fieldStyle}>
            <label style={labelStyle}>Thresholds (JSON)</label>
            <textarea
              className="noc-input"
              value={thresholds}
              onChange={e => setThresholds(e.target.value)}
              placeholder='{"warn": 80, "crit": 90}'
              style={{ resize: 'vertical', minHeight: 72, fontFamily: 'inherit', lineHeight: 1.4 }}
            />
          </div>

          {/* Notes */}
          <div style={fieldStyle}>
            <label style={labelStyle}>Notes</label>
            <textarea
              className="noc-input"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Optional notes about this card"
              style={{ resize: 'vertical', minHeight: 56, fontFamily: 'inherit', lineHeight: 1.4 }}
            />
          </div>

        </div>

        {/* Footer */}
        <div style={{
          padding: 16,
          borderTop: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          position: 'sticky',
          bottom: 0,
          background: 'var(--panel)',
        }}>
          <button className="btn-accent" onClick={handleSave}>
            Save Changes
          </button>
          <button
            className={`btn-danger${confirmRemove ? ' confirm' : ''}`}
            onClick={handleRemove}
          >
            {confirmRemove ? 'Confirm Remove?' : 'Remove Card'}
          </button>
        </div>
      </div>
    </div>
  )
}
