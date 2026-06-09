import React from 'react'
import { MetricRow, Sparkline } from '../shared.jsx'

export default function AdguardCard({ data, config, trends }) {
  if (!data) return null
  const blockPct = data.block_pct ?? (data.queries && data.blocked ? Math.round(data.blocked / data.queries * 100) : null)
  return (
    <div>
      <MetricRow label="Queries" value={data.queries ?? '—'} />
      <MetricRow label="Blocked" value={data.blocked ?? '—'} valueColor="var(--warn-color, #ffaa00)" />
      <MetricRow label="Block %" value={blockPct != null ? `${blockPct}%` : '—'} />
      <MetricRow label="Avg Latency" value={data.avg_latency != null ? `${data.avg_latency}ms` : '—'} />
      {trends?.queries && config?.graph !== false && (
        <Sparkline data={trends.queries} color={config?.graph_color} />
      )}
    </div>
  )
}
