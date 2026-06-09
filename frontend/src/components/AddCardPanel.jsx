import React, { useState, useEffect } from 'react'
import { fetchCardTypes } from '../api.js'

const CATEGORY_ORDER = ['Infrastructure', 'Security', 'Network', 'Storage', 'Media', 'Monitoring']

// Category colors
const CATEGORY_COLORS = {
  Infrastructure: 'var(--green)',
  Security:       'var(--warn)',
  Network:        '#00cfff',
  Storage:        '#a78bfa',
  Media:          '#f472b6',
  Monitoring:     '#34d399',
}

// Same icon SVG paths as CardWrapper
const ICON_PATHS = {
  Server:       'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z',
  HardDrive:    'M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 17.76 4H6.24a2 2 0 0 0-1.79 1.11zM6 16h.01M10 16h.01',
  Box:          'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16zM3.27 6.96 12 12.01l8.73-5.05M12 22.08V12',
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
  Film:         'M19.82 2H4.18A2.18 2.18 0 0 0 2 4.18v15.64A2.18 2.18 0 0 0 4.18 22h15.64A2.18 2.18 0 0 0 22 19.82V4.18A2.18 2.18 0 0 0 19.82 2zM7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5',
  Search:       'M11 3a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM21 21l-4.35-4.35',
  Download:     'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  List:         'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  HeartPulse:   'M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7z',
  ExternalLink: 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3',
  Tv:           'M2 7h20a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zM8 21h8M12 17v4',
}

function Icon({ name, size = 16, color = 'currentColor' }) {
  const path = ICON_PATHS[name]
  if (!path) return <span style={{ width: size, height: size, display: 'inline-block' }} />
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {path.split('M').filter(Boolean).map((seg, i) => (
        <path key={i} d={'M' + seg} />
      ))}
    </svg>
  )
}

export default function AddCardPanel({ onAdd, onClose }) {
  const [cardTypes, setCardTypes] = useState({})
  const [search, setSearch] = useState('')
  const [activeCategory, setActiveCategory] = useState(null)

  useEffect(() => {
    fetchCardTypes().then(setCardTypes).catch(console.error)
  }, [])

  // Group by category
  const grouped = {}
  Object.entries(cardTypes).forEach(([type, info]) => {
    const cat = info.category || 'Other'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push([type, info])
  })

  // Filter by search + active category
  const categories = CATEGORY_ORDER.filter(c => grouped[c])

  function getFiltered(cat) {
    return (grouped[cat] || []).filter(([type, info]) => {
      if (!search) return true
      const q = search.toLowerCase()
      return type.toLowerCase().includes(q) || (info.label || '').toLowerCase().includes(q) ||
             (info.description || '').toLowerCase().includes(q)
    })
  }

  const visibleCats = search
    ? categories.filter(c => getFiltered(c).length > 0)
    : (activeCategory ? [activeCategory] : categories)

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 200,
        background: 'rgba(0,0,0,0.75)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: 80,
        animation: 'fadeIn 0.15s ease',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: 'var(--panel)',
        border: '1px solid var(--line)',
        borderRadius: 4,
        width: 720,
        maxHeight: '75vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 8px 40px rgba(0,0,0,0.8)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          borderBottom: '1px solid var(--line)',
        }}>
          <span style={{
            fontSize: 11,
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            color: 'var(--green)',
          }}>
            Add Card
          </span>
          <button
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 16, fontFamily: 'inherit' }}
            onClick={onClose}
          >✕</button>
        </div>

        {/* Search + category tabs */}
        <div style={{
          padding: '10px 16px 0',
          borderBottom: '1px solid var(--line)',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}>
          <input
            className="noc-input"
            placeholder="Search card types..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            autoFocus
          />
          {!search && (
            <div style={{ display: 'flex', gap: 6, paddingBottom: 8, flexWrap: 'wrap' }}>
              <button
                className={activeCategory === null ? 'btn-accent' : 'btn-ghost'}
                style={{ fontSize: 10, padding: '2px 8px' }}
                onClick={() => setActiveCategory(null)}
              >
                All
              </button>
              {categories.map(cat => (
                <button
                  key={cat}
                  className={activeCategory === cat ? 'btn-accent' : 'btn-ghost'}
                  style={{
                    fontSize: 10,
                    padding: '2px 8px',
                    borderColor: activeCategory === cat ? undefined : CATEGORY_COLORS[cat] || 'var(--line)',
                    color: activeCategory === cat ? undefined : CATEGORY_COLORS[cat] || 'var(--txt)',
                  }}
                  onClick={() => setActiveCategory(c => c === cat ? null : cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Card grid — grouped by category */}
        <div style={{ overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {visibleCats.map(cat => {
            const items = getFiltered(cat)
            if (!items.length) return null
            const catColor = CATEGORY_COLORS[cat] || 'var(--green)'
            return (
              <div key={cat}>
                <div style={{
                  fontSize: 9,
                  textTransform: 'uppercase',
                  letterSpacing: '0.15em',
                  color: catColor,
                  marginBottom: 8,
                  paddingBottom: 4,
                  borderBottom: `1px solid ${catColor}22`,
                }}>
                  {cat}
                </div>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: 8,
                }}>
                  {items.map(([type, info]) => (
                    <div
                      key={type}
                      onClick={() => onAdd(type, info)}
                      style={{
                        background: 'var(--bg)',
                        border: '1px solid var(--line)',
                        borderLeft: `3px solid ${catColor}44`,
                        borderRadius: 3,
                        padding: '8px 10px',
                        cursor: 'pointer',
                        transition: 'border-color 0.15s, background 0.15s',
                        display: 'flex',
                        gap: 8,
                        alignItems: 'flex-start',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.borderColor = catColor
                        e.currentTarget.style.background = `${catColor}08`
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.borderColor = 'var(--line)'
                        e.currentTarget.style.borderLeftColor = `${catColor}44`
                        e.currentTarget.style.background = 'var(--bg)'
                      }}
                    >
                      <span style={{ flexShrink: 0, marginTop: 1 }}>
                        <Icon name={info.icon || 'Activity'} size={14} color={catColor} />
                      </span>
                      <div>
                        <div style={{
                          fontSize: 11,
                          fontWeight: 700,
                          color: catColor,
                          marginBottom: 2,
                          letterSpacing: '0.04em',
                        }}>
                          {info.label || type}
                        </div>
                        <div style={{
                          fontSize: 10,
                          color: 'var(--muted)',
                          lineHeight: 1.4,
                        }}>
                          {info.description || ''}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
          {visibleCats.length === 0 && (
            <div style={{ color: 'var(--muted)', fontSize: 12, padding: 8, textAlign: 'center' }}>
              No card types found for "{search}"
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
