import React from 'react'
import { MetricRow, SectionHeader, stateToColor } from '../shared.jsx'

export default function TailscaleCard({ data, config, trends }) {
  if (!data) return null
  const devices = data.devices || []
  const expiring = (data.key_expiry || [])
  return (
    <div>
      <MetricRow label="Online" value={`${data.online ?? '?'} / ${data.total ?? '?'}`} />
      {expiring.length > 0 && (
        <>
          <SectionHeader>Key Expiry</SectionHeader>
          {expiring.map((d, i) => (
            <MetricRow key={i} label={d.name || `Device ${i + 1}`} value={d.days_left != null ? `${d.days_left}d` : d.expiry || '—'} valueColor="var(--warn-color, #ffaa00)" />
          ))}
        </>
      )}
      {devices.length > 0 && (
        <>
          <SectionHeader>Devices</SectionHeader>
          {devices.slice(0, 8).map((d, i) => (
            <MetricRow
              key={i}
              label={d.name || d.hostname || `Device ${i + 1}`}
              value={d.online ? 'online' : 'offline'}
              valueColor={d.online ? 'var(--ok-color, #00ff41)' : 'var(--text-muted, #555)'}
            />
          ))}
          {devices.length > 8 && <div style={{ fontSize: 10, color: 'var(--text-muted, #555)' }}>+{devices.length - 8} more</div>}
        </>
      )}
    </div>
  )
}
