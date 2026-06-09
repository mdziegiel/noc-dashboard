import React, { useEffect, useState, useRef } from 'react'
import { MetricRow, SectionHeader, Sparkline, DonutGauge } from './shared.jsx'

// ── Raw data table (renders any flat object) ──────────────────────────────────

function RawDataTable({ data }) {
  if (!data || typeof data !== 'object') return null
  const entries = Object.entries(data)
    .filter(([k]) => !k.startsWith('_') && k !== 'state')
    .filter(([, v]) => v !== null && v !== undefined && typeof v !== 'function')

  if (!entries.length) return null

  return (
    <div style={{ marginTop: 4 }}>
      {entries.map(([k, v]) => {
        let display
        if (Array.isArray(v)) {
          display = v.length === 0 ? '[]' : `[${v.length} items]`
        } else if (typeof v === 'object') {
          display = JSON.stringify(v).slice(0, 80)
        } else {
          display = String(v)
        }
        return (
          <div key={k} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
            padding: '2px 0',
            borderBottom: '1px solid var(--card-border, #1e1e1e)',
            fontSize: 11, lineHeight: 1.6,
          }}>
            <span style={{ color: 'var(--text-muted, #555)', marginRight: 8, fontFamily: 'monospace' }}>{k}</span>
            <span style={{ color: 'var(--text-primary, #e0e0e0)', fontFamily: 'monospace', textAlign: 'right', maxWidth: '60%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {display}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ── Full-detail per-card renders ──────────────────────────────────────────────

function ProxmoxFocus({ data, trends }) {
  const vms = data.nodes || {}
  const storage = data.storage || {}
  const downVMs = data.down_vms || []
  const storageList = Object.entries(storage)

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>VMS RUNNING</div>
          <div style={{ fontSize: 28, color: 'var(--accent, #00ff41)', fontWeight: 700 }}>
            {data.vms_running ?? '?'}<span style={{ fontSize: 14, color: 'var(--text-muted, #555)' }}>/{data.vms_total ?? '?'}</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>CPU</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: (data.cpu_pct > 80) ? 'var(--warn-color, #ffaa00)' : 'var(--text-primary, #e0e0e0)' }}>
            {data.cpu_pct ?? '—'}<span style={{ fontSize: 14 }}>%</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>RAM</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary, #e0e0e0)' }}>
            {data.ram_gb ?? '—'}<span style={{ fontSize: 14 }}>GB ({data.ram_pct ?? '?'}%)</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>UPTIME</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary, #e0e0e0)' }}>
            {data.uptime_days ?? '—'}<span style={{ fontSize: 14 }}>d</span>
          </div>
        </div>
      </div>

      {trends?.cpu && (
        <>
          <SectionHeader>CPU — 48h Trend</SectionHeader>
          <Sparkline data={trends.cpu} height={60} />
        </>
      )}

      {storageList.length > 0 && (
        <>
          <SectionHeader>Storage Pools</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 4 }}>
            {storageList.map(([name, s]) => (
              <DonutGauge
                key={name}
                value={s.used_pct ?? s.pct ?? 0}
                max={100}
                color={s.used_pct > 85 ? 'var(--warn-color, #ffaa00)' : 'var(--gauge-fill-ok, #00ff41)'}
                label={name}
                size={72}
              />
            ))}
          </div>
        </>
      )}

      {downVMs.length > 0 && (
        <>
          <SectionHeader>Offline VMs</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
            {downVMs.map((vm, i) => (
              <span key={i} style={{
                fontSize: 11, padding: '2px 8px', borderRadius: 3,
                background: 'rgba(255,0,0,0.1)', color: 'var(--critical-color, #ff0000)',
              }}>{vm}</span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function DockerFocus({ data }) {
  const bad = data.bad_containers || []
  const running = data.running ?? '?'
  const total = data.total ?? '?'

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>RUNNING</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: bad.length > 0 ? 'var(--warn-color, #ffaa00)' : 'var(--accent, #00ff41)' }}>
            {running}<span style={{ fontSize: 14, color: 'var(--text-muted, #555)' }}>/{total}</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>ENVIRONMENTS</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary, #e0e0e0)' }}>
            {data.env_count ?? '—'}
          </div>
        </div>
      </div>

      {bad.length > 0 && (
        <>
          <SectionHeader>Container Issues ({bad.length})</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 4 }}>
            {bad.map((c, i) => {
              const name = typeof c === 'string' ? c : c.name || String(c)
              const st = typeof c === 'object' ? (c.state || c.status || '?') : ''
              return (
                <div key={i} style={{
                  fontSize: 11, padding: '4px 8px', borderRadius: 3,
                  background: 'rgba(255,51,51,0.08)',
                  color: 'var(--error-color, #ff3333)',
                  display: 'flex', justifyContent: 'space-between',
                }}>
                  <span>{name}</span>
                  {st && <span style={{ opacity: 0.7, fontSize: 10 }}>{st}</span>}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function WazuhFocus({ data }) {
  const down = data.down_agents || []
  const agents = data.agents || []
  const allAgents = agents.length > 0 ? agents : (down.length > 0 ? down : [])

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>AGENTS</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--accent, #00ff41)' }}>
            {data.agents_active ?? '?'}<span style={{ fontSize: 14, color: 'var(--text-muted, #555)' }}>/{data.agents_total ?? '?'}</span>
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>ALERTS 24H</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: data.alerts_24h > 0 ? 'var(--warn-color, #ffaa00)' : 'var(--text-primary, #e0e0e0)' }}>
            {data.alerts_24h ?? 0}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>HIGH SEVERITY</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: (data.high_alerts || data.high_24h) > 0 ? 'var(--critical-color, #ff0000)' : 'var(--text-primary, #e0e0e0)' }}>
            {data.high_alerts ?? data.high_24h ?? 0}
          </div>
        </div>
      </div>

      {down.length > 0 && (
        <>
          <SectionHeader>Offline Agents</SectionHeader>
          {down.map((a, i) => (
            <div key={i} style={{ fontSize: 11, color: 'var(--error-color, #ff3333)', padding: '2px 0' }}>
              {typeof a === 'string' ? a : (a.name || a.id || `Agent ${i + 1}`)}
            </div>
          ))}
        </>
      )}

      {allAgents.length > 0 && (
        <>
          <SectionHeader>All Agents</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
            {allAgents.map((a, i) => {
              const name = typeof a === 'string' ? a : (a.name || a.id || `Agent ${i + 1}`)
              const status = typeof a === 'object' ? (a.status || '?') : 'unknown'
              const isActive = typeof status === 'string' && status.toLowerCase() === 'active'
              return (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between',
                  fontSize: 11, padding: '3px 8px', borderRadius: 2,
                  background: 'rgba(255,255,255,0.02)',
                }}>
                  <span style={{ color: 'var(--text-primary, #e0e0e0)' }}>{name}</span>
                  <span style={{ color: isActive ? 'var(--ok-color, #00ff41)' : 'var(--error-color, #ff3333)' }}>
                    {status}
                  </span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function UptimeKumaFocus({ data }) {
  const monitors = data.monitors || []
  const down = data.down || []
  const up = data.up || []

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>UP</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--accent, #00ff41)' }}>
            {data.up_count ?? up.length ?? '?'}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>DOWN</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: down.length > 0 ? 'var(--critical-color, #ff0000)' : 'var(--text-primary, #e0e0e0)' }}>
            {data.down_count ?? down.length ?? 0}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>TOTAL</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-secondary, #a0a0a0)' }}>
            {data.total ?? monitors.length ?? '?'}
          </div>
        </div>
      </div>

      {down.length > 0 && (
        <>
          <SectionHeader>Down Monitors</SectionHeader>
          {down.map((m, i) => (
            <div key={i} style={{ fontSize: 11, color: 'var(--critical-color, #ff0000)', padding: '2px 0' }}>
              {typeof m === 'string' ? m : (m.name || m.url || `Monitor ${i + 1}`)}
            </div>
          ))}
        </>
      )}

      {monitors.length > 0 && (
        <>
          <SectionHeader>All Monitors</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginTop: 4 }}>
            {monitors.map((m, i) => {
              const name = typeof m === 'string' ? m : (m.name || m.url || `Monitor ${i + 1}`)
              const status = typeof m === 'object' ? (m.status || '?') : 'unknown'
              const isUp = status === 1 || status === 'up' || status === 'Up'
              const rt = typeof m === 'object' ? m.response_time : null
              return (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  fontSize: 11, padding: '3px 8px', borderRadius: 2,
                  background: 'rgba(255,255,255,0.02)',
                }}>
                  <span style={{ color: 'var(--text-primary, #e0e0e0)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>{name}</span>
                  <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                    {rt != null && <span style={{ color: 'var(--text-muted, #555)', fontSize: 10 }}>{rt}ms</span>}
                    <span style={{ color: isUp ? 'var(--ok-color, #00ff41)' : 'var(--critical-color, #ff0000)' }}>
                      {isUp ? 'UP' : 'DOWN'}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function CrowdSecFocus({ data }) {
  const bouncers = data.bouncers || []
  return (
    <div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>ACTIVE BANS</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--accent, #00ff41)' }}>
            {data.active_bans ?? data.bans ?? '?'}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>DETECTIONS 24H</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary, #e0e0e0)' }}>
            {data.decisions_24h ?? data.detections_24h ?? 0}
          </div>
        </div>
      </div>

      {data.top_attackers && data.top_attackers.length > 0 && (
        <>
          <SectionHeader>Top Attackers</SectionHeader>
          {data.top_attackers.slice(0, 10).map((a, i) => {
            const ip = typeof a === 'string' ? a : (a.ip || a.source || String(a))
            const count = typeof a === 'object' ? (a.count || a.decisions || '') : ''
            return (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', fontSize: 11,
                padding: '2px 0', color: 'var(--text-primary, #e0e0e0)',
                borderBottom: '1px solid var(--card-border, #1e1e1e)',
              }}>
                <span style={{ fontFamily: 'monospace' }}>{ip}</span>
                {count && <span style={{ color: 'var(--warn-color, #ffaa00)' }}>{count}</span>}
              </div>
            )
          })}
        </>
      )}

      {bouncers.length > 0 && (
        <>
          <SectionHeader>Bouncers</SectionHeader>
          {bouncers.map((b, i) => {
            const name = typeof b === 'string' ? b : (b.name || String(b))
            const status = typeof b === 'object' ? (b.status || b.state || '') : ''
            const isOk = !status || status.toLowerCase() === 'ok' || status.toLowerCase() === 'up'
            return (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', fontSize: 11,
                padding: '2px 0', borderBottom: '1px solid var(--card-border, #1e1e1e)',
              }}>
                <span style={{ color: 'var(--text-primary, #e0e0e0)' }}>{name}</span>
                {status && <span style={{ color: isOk ? 'var(--ok-color, #00ff41)' : 'var(--warn-color, #ffaa00)' }}>{status}</span>}
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}

function AdguardFocus({ data, trends }) {
  return (
    <div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>QUERIES 24H</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary, #e0e0e0)' }}>
            {(data.queries ?? data.queries_24h ?? 0).toLocaleString()}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>BLOCKED %</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--accent, #00ff41)' }}>
            {data.block_pct != null ? `${data.block_pct.toFixed(1)}%` : '—'}
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted, #555)', letterSpacing: '0.08em', marginBottom: 2 }}>BLOCKED 24H</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary, #e0e0e0)' }}>
            {(data.blocked_24h ?? data.blocked ?? 0).toLocaleString()}
          </div>
        </div>
      </div>

      {trends?.block_pct && (
        <>
          <SectionHeader>Block % — 48h Trend</SectionHeader>
          <Sparkline data={trends.block_pct} height={60} />
        </>
      )}

      {data.top_blocked && data.top_blocked.length > 0 && (
        <>
          <SectionHeader>Top Blocked Domains</SectionHeader>
          {data.top_blocked.slice(0, 10).map((d, i) => {
            const domain = typeof d === 'string' ? d : (d.name || d.domain || String(d))
            const count = typeof d === 'object' ? (d.count || '') : ''
            return (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', fontSize: 11,
                padding: '2px 0', borderBottom: '1px solid var(--card-border, #1e1e1e)',
              }}>
                <span style={{ color: 'var(--text-primary, #e0e0e0)', fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '80%' }}>{domain}</span>
                {count && <span style={{ color: 'var(--text-muted, #555)' }}>{count}</span>}
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}

function PbsFocus({ data }) {
  const tasks = data.tasks || data.recent_tasks || []
  return (
    <div>
      <MetricRow label="Last Backup" value={data.last_backup || data.last_run || '—'} />
      <MetricRow label="Failed Tasks" value={data.failed_tasks ?? 0} valueColor={(data.failed_tasks ?? 0) > 0 ? 'var(--critical-color, #ff0000)' : undefined} />
      <MetricRow label="Datastore" value={data.datastore_name || '—'} />
      <MetricRow label="Used" value={data.used_pct != null ? `${data.used_pct}%` : (data.used_gb ? `${data.used_gb} GB` : '—')} />

      {tasks.length > 0 && (
        <>
          <SectionHeader>Recent Tasks</SectionHeader>
          {tasks.slice(0, 15).map((t, i) => {
            const status = t.status || t.state || '?'
            const isOk = status.toLowerCase() === 'ok' || status.toLowerCase() === 'ok (no-changes)'
            return (
              <div key={i} style={{
                fontSize: 11, padding: '3px 0',
                borderBottom: '1px solid var(--card-border, #1e1e1e)',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span style={{ color: 'var(--text-primary, #e0e0e0)', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '70%' }}>
                  {t.guest || t.id || t.upid || `Task ${i + 1}`}
                </span>
                <span style={{ color: isOk ? 'var(--ok-color, #00ff41)' : 'var(--error-color, #ff3333)', flexShrink: 0 }}>
                  {status}
                </span>
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}

function GenericFocus({ data, trends }) {
  const trendKeys = Object.keys(trends || {})
  return (
    <div>
      {trendKeys.length > 0 && (
        <>
          {trendKeys.map(k => (
            <div key={k}>
              <SectionHeader>{k} — 48h Trend</SectionHeader>
              <Sparkline data={trends[k]} height={60} />
            </div>
          ))}
        </>
      )}
      <SectionHeader>Raw Data</SectionHeader>
      <RawDataTable data={data} />
    </div>
  )
}

// ── Focus card router ─────────────────────────────────────────────────────────

function FocusCardContent({ cardType, data, trends }) {
  const t = trends || data?._trends || {}
  switch (cardType) {
    case 'proxmox':
    case 'proxmox_storage':
      return <ProxmoxFocus data={data} trends={t} />
    case 'docker':
      return <DockerFocus data={data} />
    case 'wazuh':
      return <WazuhFocus data={data} />
    case 'uptime_kuma':
      return <UptimeKumaFocus data={data} />
    case 'crowdsec':
      return <CrowdSecFocus data={data} />
    case 'adguard':
      return <AdguardFocus data={data} trends={t} />
    case 'pbs':
      return <PbsFocus data={data} />
    default:
      return <GenericFocus data={data} trends={t} />
  }
}

// ── Main FocusModal ───────────────────────────────────────────────────────────

export default function FocusModal({ card, data, onClose }) {
  const [liveData, setLiveData] = useState(data)
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState(new Date())

  // Close on Escape and lock body scroll
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  function handleBackdrop(e) {
    if (e.target === e.currentTarget) onClose()
  }

  function doRefresh() {
    setRefreshing(true)
    fetch(`/api/data/${card.type}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) { setLiveData(d); setLastRefresh(new Date()) }
        setRefreshing(false)
      })
      .catch(() => setRefreshing(false))
  }

  const trends = liveData?._trends || null
  const state = liveData?.state
  const elapsed = liveData?._elapsed

  const stateColor = {
    ok: 'var(--ok-color, #00ff41)',
    warn: 'var(--warn-color, #ffaa00)',
    crit: 'var(--critical-color, #ff0000)',
    error: 'var(--error-color, #ff3333)',
  }[state] || 'var(--text-muted, #555)'

  return (
    <div
      onClick={handleBackdrop}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(6px)',
        zIndex: 9000, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
    >
      <div style={{
        background: 'var(--card-background, #111)',
        border: `1px solid ${stateColor}44`,
        borderLeft: `3px solid ${stateColor}`,
        borderRadius: 6, width: '100%', maxWidth: 820,
        maxHeight: '88vh', overflowY: 'auto', position: 'relative',
        boxShadow: `0 8px 40px rgba(0,0,0,0.8), 0 0 0 1px ${stateColor}22`,
      }}>
        {/* Modal header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px 10px',
          borderBottom: '1px solid var(--card-border, #1e1e1e)',
          position: 'sticky', top: 0,
          background: 'var(--card-background, #111)',
          zIndex: 1,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              fontSize: 14, fontWeight: 700,
              color: 'var(--accent, #00ff41)',
              letterSpacing: '0.1em', textTransform: 'uppercase',
            }}>
              {card.title || card.type}
            </span>
            <span style={{
              fontSize: 10, padding: '2px 8px', borderRadius: 3,
              background: `${stateColor}18`, color: stateColor,
              fontWeight: 700, letterSpacing: '0.08em',
            }}>
              {state?.toUpperCase() || '—'}
            </span>
            {elapsed != null && (
              <span style={{ fontSize: 10, color: 'var(--text-muted, #555)' }}>
                {elapsed}s
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 10, color: 'var(--text-muted, #555)' }}>
              {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
            <button
              onClick={doRefresh}
              disabled={refreshing}
              style={{
                background: 'none', border: '1px solid var(--card-border, #1e1e1e)',
                color: refreshing ? 'var(--text-muted, #555)' : 'var(--text-secondary, #a0a0a0)',
                cursor: refreshing ? 'default' : 'pointer',
                fontSize: 10, padding: '3px 10px',
                borderRadius: 3, fontFamily: 'inherit', letterSpacing: '0.06em',
                transition: 'color 0.15s',
              }}
            >
              {refreshing ? '...' : '↻ REFRESH'}
            </button>
            <button
              onClick={onClose}
              style={{
                background: 'none', border: 'none',
                color: 'var(--text-muted, #555)',
                cursor: 'pointer', fontSize: 18, lineHeight: 1,
                padding: '2px 6px', fontFamily: 'inherit',
                transition: 'color 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary, #e0e0e0)'}
              onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted, #555)'}
            >
              &times;
            </button>
          </div>
        </div>

        {/* Modal body — card-specific expanded content */}
        <div style={{ padding: '16px 20px', fontSize: 13, color: 'var(--text-primary, #ccc)' }}>
          {liveData ? (
            <FocusCardContent cardType={card.type} data={liveData} trends={trends} />
          ) : (
            <span style={{ color: 'var(--text-muted, #555)', fontSize: 12 }}>No data available.</span>
          )}

          {/* Always show raw data at the bottom as a collapse section */}
          <details style={{ marginTop: 20 }}>
            <summary style={{
              fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em',
              color: 'var(--text-muted, #555)', cursor: 'pointer', padding: '4px 0',
              userSelect: 'none',
            }}>
              Raw Collector Data
            </summary>
            <div style={{ marginTop: 6 }}>
              <RawDataTable data={liveData} />
            </div>
          </details>
        </div>
      </div>
    </div>
  )
}
