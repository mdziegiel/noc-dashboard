import React from 'react'
import { MetricRow, SectionHeader, stateToColor } from '../shared.jsx'

export default function DockerCard({ data, config, trends }) {
  if (!data) return null
  const bad = data.bad_containers || []
  return (
    <div>
      <MetricRow label="Running" value={`${data.running ?? '?'} / ${data.total ?? '?'}`} />
      <MetricRow label="Environments" value={data.env_count ?? '—'} />
      {bad.length > 0 && (
        <>
          <SectionHeader>Issues</SectionHeader>
          {bad.map((c, i) => (
            <div key={i} style={{ fontSize: 10, color: 'var(--error-color, #ff3333)', padding: '1px 0' }}>
              {typeof c === 'string' ? c : `${c.name} (${c.state || c.status || '?'})`}
            </div>
          ))}
        </>
      )}
    </div>
  )
}
