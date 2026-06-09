import React from 'react'
import { MetricRow, Sparkline } from '../shared.jsx'

export default function SabnzbdCard({ data, config, trends }) {
  if (!data) return null
  return (
    <div>
      <MetricRow label="Status" value={data.status ?? '—'} />
      <MetricRow label="Queue" value={data.queue_slots ?? data.queue ?? '—'} />
      <MetricRow label="Speed" value={data.speed ?? '—'} valueColor={data.speed && data.speed !== '0 B/s' ? 'var(--ok-color, #00ff41)' : undefined} />
      <MetricRow label="Today" value={data.day_gb != null ? `${data.day_gb} GB` : '—'} />
      {trends?.speed && config?.graph !== false && (
        <Sparkline data={trends.speed} color={config?.graph_color} />
      )}
    </div>
  )
}
