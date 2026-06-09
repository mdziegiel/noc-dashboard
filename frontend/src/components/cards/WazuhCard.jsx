import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function WazuhCard({ data, config, trends }) {
  if (!data) return null
  const down = data.down_agents || []
  return (
    <div>
      <MetricRow label="Agents Active" value={`${data.agents_active ?? '?'} / ${data.agents_total ?? '?'}`} />
      <MetricRow label="Alerts 24h" value={data.alerts_24h ?? 0} valueColor={data.alerts_24h > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      <MetricRow label="High Alerts" value={data.high_alerts ?? 0} valueColor={data.high_alerts > 0 ? 'var(--error-color, #ff3333)' : undefined} />
      {down.length > 0 && (
        <>
          <SectionHeader>Down Agents</SectionHeader>
          {down.map((a, i) => (
            <div key={i} style={{ fontSize: 10, color: 'var(--error-color, #ff3333)', padding: '1px 0' }}>
              {typeof a === 'string' ? a : a.name || a.id || `Agent ${i + 1}`}
            </div>
          ))}
        </>
      )}
    </div>
  )
}
