import React, { useState, useEffect, useRef, useCallback } from 'react'
import {
  fetchIntegrations, saveIntegration, deleteIntegration,
  testIntegration, fetchIntegrationStatus
} from '../api.js'

const CATEGORY_ORDER = ['Infrastructure', 'Security', 'Network', 'Storage', 'Media', 'Monitoring']
const CATEGORY_COLORS = {
  Infrastructure: 'var(--green)',
  Security:       'var(--warn)',
  Network:        '#00cfff',
  Storage:        '#a78bfa',
  Media:          '#f472b6',
  Monitoring:     '#34d399',
}

// Icon SVG paths (same set as AddCardPanel)
const ICON_PATHS = {
  Server:       'M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z',
  HardDrive:    'M22 12H2M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 17.76 4H6.24a2 2 0 0 0-1.79 1.11zM6 16h.01M10 16h.01',
  Box:          'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16zM3.27 6.96 12 12.01l8.73-5.05M12 22.08V12',
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
  Settings:     'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
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

function StatusDot({ ok, loading, error }) {
  if (loading) return (
    <span style={{
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: 'var(--muted)', flexShrink: 0,
    }} title="Checking..." />
  )
  return (
    <span
      title={ok ? 'Connected' : (error || 'Unreachable')}
      style={{
        display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
        flexShrink: 0,
        background: ok ? 'var(--green)' : 'var(--crit, #ff3333)',
        boxShadow: ok ? '0 0 4px var(--green)' : '0 0 4px var(--crit, #ff3333)',
      }}
    />
  )
}

// Single integration config form — rendered in a slide-in detail panel
function IntegrationConfigForm({ itype, info, status, onSave, onDelete, onClose }) {
  const [values, setValues] = useState({})
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testResult, setTestResult] = useState(null)  // {ok, message, elapsed}
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const catColor = CATEGORY_COLORS[info.category] || 'var(--green)'

  // Initialize from current_values
  useEffect(() => {
    const init = {}
    for (const field of info.fields || []) {
      init[field.key] = info.current_values?.[field.key] || ''
    }
    setValues(init)
  }, [itype, info])

  async function handleTest() {
    setTesting(true)
    setTestResult(null)
    try {
      // Pass non-masked values
      const testFields = {}
      for (const [k, v] of Object.entries(values)) {
        if (v && v !== '••••••••') testFields[k] = v
      }
      const res = await testIntegration(itype, testFields)
      setTestResult(res)
    } catch (e) {
      setTestResult({ ok: false, message: e.message, elapsed: 0 })
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    try {
      await saveIntegration(itype, values)
      onSave(itype)
    } catch (e) {
      setTestResult({ ok: false, message: `Save failed: ${e.message}`, elapsed: 0 })
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!deleteConfirm) { setDeleteConfirm(true); return }
    try {
      await deleteIntegration(itype)
      onDelete(itype)
    } catch (e) {
      setTestResult({ ok: false, message: `Delete failed: ${e.message}`, elapsed: 0 })
      setDeleteConfirm(false)
    }
  }

  const hasFields = (info.fields || []).length > 0
  const isAlwaysAvailable = info.always_available && !hasFields

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      padding: '20px 24px',
      overflowY: 'auto',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <Icon name={info.icon || 'Activity'} size={20} color={catColor} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: catColor, letterSpacing: '0.04em' }}>
            {info.label}
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
            {info.description}
          </div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          {info.configured && status && (
            <StatusDot ok={status.ok} error={status.error} />
          )}
          <span style={{
            fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.12em',
            color: info.configured ? (status?.ok ? 'var(--green)' : 'var(--crit,#ff3333)') : 'var(--muted)',
            border: `1px solid ${info.configured ? (status?.ok ? 'var(--green)' : 'var(--crit,#ff3333)') : 'var(--muted)'}`,
            padding: '2px 6px', borderRadius: 2,
          }}>
            {info.configured ? (status?.ok ? 'Connected' : (status ? 'Error' : 'Configured')) : 'Not Configured'}
          </span>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 16, fontFamily: 'inherit', padding: '0 4px' }}
        >✕</button>
      </div>

      {/* Live error message if status is bad */}
      {info.configured && status && !status.ok && (
        <div style={{
          background: 'rgba(255,51,51,0.08)', border: '1px solid rgba(255,51,51,0.3)',
          borderRadius: 3, padding: '8px 12px', marginBottom: 16,
          fontSize: 11, color: 'var(--crit, #ff3333)',
        }}>
          Connection error: {status.error}
          {status.elapsed ? ` (${status.elapsed}s)` : ''}
        </div>
      )}

      {isAlwaysAvailable ? (
        <div style={{
          padding: '16px 20px', background: 'rgba(0,255,65,0.04)',
          border: '1px solid rgba(0,255,65,0.15)', borderRadius: 3,
          fontSize: 11, color: 'var(--muted)',
        }}>
          This integration requires no credentials — it uses public feeds and is always available.
        </div>
      ) : (
        <>
          {/* Fields */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
            {(info.fields || []).map(field => (
              <div key={field.key}>
                <label style={{
                  display: 'block', fontSize: 10, textTransform: 'uppercase',
                  letterSpacing: '0.1em', color: 'var(--muted)', marginBottom: 5,
                }}>
                  {field.label}
                </label>
                <input
                  className="noc-input"
                  type={field.type === 'password' ? 'password' : 'text'}
                  placeholder={field.placeholder || ''}
                  value={values[field.key] || ''}
                  onChange={e => setValues(v => ({ ...v, [field.key]: e.target.value }))}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  autoComplete="off"
                />
              </div>
            ))}
          </div>

          {/* Test result */}
          {testResult && (
            <div style={{
              background: testResult.ok ? 'rgba(0,255,65,0.06)' : 'rgba(255,51,51,0.08)',
              border: `1px solid ${testResult.ok ? 'rgba(0,255,65,0.25)' : 'rgba(255,51,51,0.3)'}`,
              borderRadius: 3, padding: '8px 12px', marginBottom: 16,
              fontSize: 11,
              color: testResult.ok ? 'var(--green)' : 'var(--crit, #ff3333)',
            }}>
              {testResult.ok ? '✓ ' : '✗ '}{testResult.message}
              {testResult.elapsed ? ` (${testResult.elapsed}s)` : ''}
            </div>
          )}

          {/* Action buttons */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              className="btn-ghost"
              onClick={handleTest}
              disabled={testing}
              style={{ fontSize: 11, padding: '5px 14px' }}
            >
              {testing ? 'Testing...' : 'Test Connection'}
            </button>
            <button
              className="btn-accent"
              onClick={handleSave}
              disabled={saving}
              style={{ fontSize: 11, padding: '5px 14px' }}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            {info.configured && (
              <button
                onClick={handleDelete}
                style={{
                  marginLeft: 'auto',
                  background: 'none',
                  border: `1px solid ${deleteConfirm ? 'var(--crit,#ff3333)' : 'var(--line)'}`,
                  color: deleteConfirm ? 'var(--crit,#ff3333)' : 'var(--muted)',
                  cursor: 'pointer', fontSize: 11, padding: '5px 12px',
                  borderRadius: 3, fontFamily: 'inherit',
                  transition: 'all 0.15s',
                }}
                onMouseLeave={() => setDeleteConfirm(false)}
              >
                {deleteConfirm ? 'Click again to clear config' : 'Clear Config'}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export default function IntegrationsPage({ onClose }) {
  const [integrations, setIntegrations] = useState({})
  const [status, setStatus] = useState({})
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [activeCategory, setActiveCategory] = useState(null)
  const [search, setSearch] = useState('')
  const statusTimerRef = useRef(null)

  const loadStatus = useCallback(async () => {
    try {
      const stat = await fetchIntegrationStatus()
      setStatus(stat)
    } catch (e) {
      console.error('Integration status load error:', e)
    }
  }, [])

  const loadAll = useCallback(async () => {
    try {
      const ints = await fetchIntegrations()
      setIntegrations(ints)
      // Pre-select first configured or first overall without waiting for health checks.
      setSelected(prev => {
        if (prev) return prev
        const configured = Object.entries(ints).find(([, v]) => v.configured)
        const first = configured || Object.entries(ints)[0]
        return first ? first[0] : prev
      })
      setLoading(false)
      loadStatus()
    } catch (e) {
      console.error('IntegrationsPage load error:', e)
      setLoading(false)
    }
  }, [loadStatus])

  useEffect(() => {
    loadAll()
    // Auto-refresh status every 60 seconds. Sidebar structure is already rendered;
    // only the status dots update as these responses come back.
    statusTimerRef.current = setInterval(loadStatus, 60000)
    return () => clearInterval(statusTimerRef.current)
  }, [loadAll, loadStatus])

  function handleSaved(itype) {
    // Reload integrations to pick up new configured state
    fetchIntegrations().then(ints => {
      setIntegrations(ints)
      setSelected(itype)
    })
    // Clear status cache for this type so next refresh re-checks
    fetchIntegrationStatus().then(setStatus).catch(() => {})
  }

  function handleDeleted(itype) {
    fetchIntegrations().then(setIntegrations)
    setStatus(s => { const n = { ...s }; delete n[itype]; return n })
  }

  // Group by category
  const grouped = {}
  Object.entries(integrations).forEach(([itype, info]) => {
    const cat = info.category || 'Other'
    if (!grouped[cat]) grouped[cat] = []
    grouped[cat].push([itype, info])
  })

  const categories = CATEGORY_ORDER.filter(c => grouped[c])

  function getFiltered(cat) {
    const q = search.toLowerCase()
    return (grouped[cat] || []).filter(([itype, info]) => {
      if (!q) return true
      return itype.toLowerCase().includes(q) || (info.label || '').toLowerCase().includes(q)
    })
  }

  const visibleCats = search
    ? categories.filter(c => getFiltered(c).length > 0)
    : (activeCategory ? [activeCategory] : categories)

  // Count configured per category
  function configuredCount(cat) {
    return (grouped[cat] || []).filter(([, v]) => v.configured).length
  }

  const selectedInfo = integrations[selected]
  const selectedStatus = status[selected]

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 300,
        background: 'rgba(0,0,0,0.8)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        animation: 'fadeIn 0.15s ease',
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: 'var(--panel)',
        border: '1px solid var(--line)',
        borderRadius: 4,
        width: 900,
        height: '80vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 12px 60px rgba(0,0,0,0.9)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          padding: '10px 16px',
          borderBottom: '1px solid var(--line)',
          gap: 10,
          flexShrink: 0,
        }}>
          <Icon name="Settings" size={14} color="var(--green)" />
          <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'var(--green)' }}>
            Settings / Integrations
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: 'var(--muted)' }}>
              {Object.values(integrations).filter(v => v.configured).length} of {Object.keys(integrations).length} configured
            </span>
            <button
              style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 16, fontFamily: 'inherit' }}
              onClick={onClose}
            >✕</button>
          </div>
        </div>

        {/* Body: left panel (list) + right panel (config form) */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          {/* Left list panel */}
          <div style={{
            width: 280,
            borderRight: '1px solid var(--line)',
            display: 'flex',
            flexDirection: 'column',
            flexShrink: 0,
            overflow: 'hidden',
          }}>
            {/* Search */}
            <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--line)' }}>
              <input
                className="noc-input"
                placeholder="Filter integrations..."
                value={search}
                onChange={e => { setSearch(e.target.value); setActiveCategory(null) }}
                style={{ width: '100%', boxSizing: 'border-box' }}
              />
            </div>

            {/* Category tabs */}
            {!search && (
              <div style={{ padding: '8px 12px', display: 'flex', flexWrap: 'wrap', gap: 4, borderBottom: '1px solid var(--line)' }}>
                <button
                  className={activeCategory === null ? 'btn-accent' : 'btn-ghost'}
                  style={{ fontSize: 9, padding: '1px 7px' }}
                  onClick={() => setActiveCategory(null)}
                >
                  All
                </button>
                {categories.map(cat => (
                  <button
                    key={cat}
                    className={activeCategory === cat ? 'btn-accent' : 'btn-ghost'}
                    style={{
                      fontSize: 9, padding: '1px 7px',
                      borderColor: activeCategory === cat ? undefined : (CATEGORY_COLORS[cat] || 'var(--line)') + '66',
                      color: activeCategory === cat ? undefined : CATEGORY_COLORS[cat] || 'var(--txt)',
                    }}
                    onClick={() => setActiveCategory(c => c === cat ? null : cat)}
                  >
                    {cat.slice(0, 5)}{configuredCount(cat) > 0 ? ` ·${configuredCount(cat)}` : ''}
                  </button>
                ))}
              </div>
            )}

            {/* Integration list */}
            <div style={{ overflowY: 'auto', flex: 1 }}>
              {loading ? (
                <div style={{ padding: 20, color: 'var(--muted)', fontSize: 11, textAlign: 'center' }}>
                  Loading...
                </div>
              ) : (
                visibleCats.map(cat => {
                  const items = getFiltered(cat)
                  if (!items.length) return null
                  const catColor = CATEGORY_COLORS[cat] || 'var(--green)'
                  return (
                    <div key={cat}>
                      <div style={{
                        padding: '6px 12px 3px',
                        fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.15em',
                        color: catColor, borderBottom: `1px solid ${catColor}18`,
                        background: `${catColor}06`,
                      }}>
                        {cat}
                      </div>
                      {items.map(([itype, info]) => {
                        const iStatus = status[itype]
                        const isSelected = selected === itype
                        return (
                          <div
                            key={itype}
                            onClick={() => setSelected(itype)}
                            style={{
                              padding: '8px 12px',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 10,
                              background: isSelected ? `${catColor}12` : 'transparent',
                              borderLeft: isSelected ? `3px solid ${catColor}` : '3px solid transparent',
                              borderBottom: '1px solid var(--line)26',
                              transition: 'background 0.1s',
                            }}
                            onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = `${catColor}08` }}
                            onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
                          >
                            <Icon name={info.icon || 'Activity'} size={13} color={info.configured ? catColor : 'var(--muted)'} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div style={{
                                fontSize: 11,
                                color: info.configured ? (isSelected ? catColor : 'var(--txt)') : 'var(--muted)',
                                fontWeight: info.configured ? 600 : 400,
                                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                              }}>
                                {info.label}
                              </div>
                            </div>
                            {/* Status indicator */}
                            {info.configured && (
                              <StatusDot
                                ok={iStatus?.ok}
                                loading={!iStatus}
                                error={iStatus?.error}
                              />
                            )}
                            {!info.configured && (
                              <span style={{ fontSize: 9, color: 'var(--muted)', letterSpacing: '0.05em' }}>—</span>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )
                })
              )}
            </div>
          </div>

          {/* Right config panel */}
          <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            {selectedInfo ? (
              <IntegrationConfigForm
                key={selected}
                itype={selected}
                info={selectedInfo}
                status={selectedStatus}
                onSave={handleSaved}
                onDelete={handleDeleted}
                onClose={onClose}
              />
            ) : (
              <div style={{
                flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--muted)', fontSize: 12,
              }}>
                Select an integration to configure
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
