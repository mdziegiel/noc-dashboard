import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function CrowdsecCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: bans, local_bans, detections_24h, top (list)
  const scenarios = data.top || data.top_scenarios || []
  return (
    <div>
      <MetricRow
        label="Total Bans"
        value={data.bans ?? data.total_bans ?? '—'}
        valueColor={data.bans > 0 ? 'var(--warn-color, #ffaa00)' : undefined}
      />
      <MetricRow label="Local Bans" value={data.local_bans ?? '—'} />
      <MetricRow
        label="Detections 24h"
        value={data.detections_24h ?? '—'}
        valueColor={data.detections_24h > 0 ? 'var(--warn-color, #ffaa00)' : undefined}
      />
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
