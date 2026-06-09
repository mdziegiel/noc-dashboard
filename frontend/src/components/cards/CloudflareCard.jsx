import React from 'react'
import { MetricRow, SectionHeader, Sparkline } from '../shared.jsx'

export default function CloudflareCard({ data, config, trends }) {
  if (!data) return null
  return (
    <div>
      <MetricRow label="Requests" value={data.requests ?? '—'} />
      <MetricRow label="Threats" value={data.threats ?? 0} valueColor={data.threats > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      <MetricRow label="Bandwidth" value={data.bandwidth ?? data.bandwidth_gb != null ? `${data.bandwidth_gb} GB` : (data.bandwidth || '—')} />
      <MetricRow label="WAF Events" value={data.waf_events ?? 0} valueColor={data.waf_events > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      {trends?.requests && config?.graph !== false && (
        <Sparkline data={trends.requests} color={config?.graph_color} />
      )}
    </div>
  )
}
