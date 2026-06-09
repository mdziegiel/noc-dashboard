import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function CrowdsecCard({ data, config, trends }) {
  if (!data) return null
  const scenarios = data.top_scenarios || []
  return (
    <div>
      <MetricRow label="Total Bans" value={data.total_bans ?? '—'} />
      <MetricRow label="Local Bans" value={data.local_bans ?? '—'} />
      <MetricRow label="Detections 24h" value={data.detections_24h ?? '—'} valueColor={data.detections_24h > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      {scenarios.length > 0 && (
        <>
          <SectionHeader>Top Scenarios</SectionHeader>
          {scenarios.map((s, i) => (
            <MetricRow
              key={i}
              label={typeof s === 'string' ? s : s.name || `Scenario ${i + 1}`}
              value={typeof s === 'object' ? s.count ?? '—' : undefined}
            />
          ))}
        </>
      )}
    </div>
  )
}
