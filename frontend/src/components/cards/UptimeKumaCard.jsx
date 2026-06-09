import React from 'react'
import { MetricRow, SectionHeader, stateToColor } from '../shared.jsx'

function MonitorBlock({ status }) {
  const color = status === 'up' || status === 1
    ? 'var(--ok-color, #00ff41)'
    : status === 'down' || status === 0
      ? 'var(--error-color, #ff3333)'
      : 'var(--text-muted, #555)'
  return (
    <div style={{
      width: 10,
      height: 10,
      background: color,
      borderRadius: 1,
      flexShrink: 0,
    }} title={String(status)} />
  )
}

export default function UptimeKumaCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: up, total, down (list of names), certs [{name, days, valid}], status_map {name: 0|1}
  const statusMap = data.status_map || {}
  const certs = data.certs || data.cert_expiry || []
  const down = Array.isArray(data.down) ? data.down : []
  const total = data.total ?? (data.up ?? 0) + down.length
  const expiring = certs.filter(c => c.days < 30)

  return (
    <div>
      <MetricRow
        label="Monitors Up"
        value={`${data.up ?? '—'} / ${total}`}
        valueColor={down.length > 0 ? 'var(--error-color, #ff3333)' : 'var(--ok-color, #00ff41)'}
      />
      {down.length > 0 && (
        <MetricRow
          label="Down"
          value={down.length}
          valueColor="var(--error-color, #ff3333)"
        />
      )}
      {Object.keys(statusMap).length > 0 && (
        <>
          <SectionHeader>Monitor Grid</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 4 }}>
            {Object.entries(statusMap).map(([name, status]) => (
              <MonitorBlock key={name} status={status} />
            ))}
          </div>
        </>
      )}
      {down.length > 0 && (
        <>
          <SectionHeader>Down</SectionHeader>
          {down.map((name, i) => (
            <div key={i} style={{ fontSize: 10, color: 'var(--error-color, #ff3333)', padding: '1px 0' }}>
              {typeof name === 'string' ? name : name.name || `Monitor ${i + 1}`}
            </div>
          ))}
        </>
      )}
      {expiring.length > 0 && (
        <>
          <SectionHeader>Cert Expiry</SectionHeader>
          {expiring.map((c, i) => (
            <MetricRow
              key={i}
              label={c.name || `cert ${i + 1}`}
              value={c.days != null ? `${c.days}d` : '—'}
              valueColor={c.days < 14 ? 'var(--error-color, #ff3333)' : 'var(--warn-color, #ffaa00)'}
            />
          ))}
        </>
      )}
    </div>
  )
}
