import React from 'react'
import { MetricRow } from '../shared.jsx'

export default function RadarrCard({ data, config, trends }) {
  if (!data) return null
  return (
    <div>
      <MetricRow label="Movies" value={`${data.monitored ?? '?'} / ${data.total ?? '?'} monitored`} />
      <MetricRow label="Queue" value={data.queue ?? 0} valueColor={data.queue > 0 ? 'var(--ok-color, #00ff41)' : undefined} />
      <MetricRow label="Missing" value={data.missing ?? 0} valueColor={data.missing > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
    </div>
  )
}
