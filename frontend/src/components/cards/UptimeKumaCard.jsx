import React from 'react'
import { MetricRow, SectionHeader, stateToColor } from '../shared.jsx'

function MonitorBlock({ status }) {
  const color = status === 'up' ? 'var(--ok-color, #00ff41)'
    : status === 'down' ? 'var(--error-color, #ff3333)'
    : 'var(--text-muted, #555)'
  return (
    <div style={{
      width: 10,
      height: 10,
      background: color,
      borderRadius: 1,
      flexShrink: 0,
    }} title={status} />
  )
}

export default function UptimeKumaCard({ data, config, trends }) {
  if (!data) return null
  const monitors = data.monitors || []
  const certs = data.cert_expiry || []
  return (
    <div>
      <MetricRow label="Up" value={data.up ?? '—'} valueColor="var(--ok-color, #00ff41)" />
      <MetricRow label="Down" value={data.down ?? 0} valueColor={data.down > 0 ? 'var(--error-color, #ff3333)' : undefined} />
      {monitors.length > 0 && (
        <>
          <SectionHeader>Monitors</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 4 }}>
            {monitors.map((m, i) => (
              <MonitorBlock key={i} status={m.status || (m.active ? 'up' : 'down')} />
            ))}
          </div>
        </>
      )}
      {certs.length > 0 && (
        <>
          <SectionHeader>Cert Expiry</SectionHeader>
          {certs.map((c, i) => (
            <MetricRow
              key={i}
              label={c.name || c.host || `cert ${i + 1}`}
              value={c.days_left != null ? `${c.days_left}d` : c.expiry || '—'}
              valueColor={c.days_left < 14 ? 'var(--warn-color, #ffaa00)' : undefined}
            />
          ))}
        </>
      )}
    </div>
  )
}
