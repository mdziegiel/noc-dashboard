import React from 'react'
import { MetricRow, SectionHeader, stateToColor } from '../shared.jsx'

export default function DockerCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: running, total, envs, bad (list of strings)
  const bad = data.bad || data.bad_containers || []
  return (
    <div>
      <MetricRow
        label="Running"
        value={`${data.running ?? '?'} / ${data.total ?? '?'}`}
        valueColor={bad.length > 0 ? 'var(--warn-color, #ffaa00)' : 'var(--ok-color, #00ff41)'}
      />
      <MetricRow label="Environments" value={data.envs ?? data.env_count ?? '—'} />
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
