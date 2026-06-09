import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function WazuhCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: active, total, down (list), alerts_24h, high_24h
  const down = data.down || data.down_agents || []
  return (
    <div>
      <MetricRow
        label="Agents"
        value={`${data.active ?? data.agents_active ?? '?'} / ${data.total ?? data.agents_total ?? '?'}`}
        valueColor={down.length > 0 ? 'var(--warn-color, #ffaa00)' : 'var(--ok-color, #00ff41)'}
      />
      <MetricRow
        label="Alerts 24h"
        value={data.alerts_24h ?? 0}
        valueColor={data.alerts_24h > 500 ? 'var(--warn-color, #ffaa00)' : undefined}
      />
      <MetricRow
        label="High Severity"
        value={data.high_24h ?? data.high_alerts ?? 0}
        valueColor={(data.high_24h || data.high_alerts) > 0 ? 'var(--error-color, #ff3333)' : undefined}
      />
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
