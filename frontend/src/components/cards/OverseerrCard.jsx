import React from 'react'
import { MetricRow } from '../shared.jsx'

export default function OverseerrCard({ data, config, trends }) {
  if (!data) return null
  return (
    <div>
      <MetricRow label="Pending" value={data.pending ?? '—'} valueColor={data.pending > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      <MetricRow label="Approved" value={data.approved ?? '—'} />
      <MetricRow label="Available" value={data.available ?? '—'} valueColor="var(--ok-color, #00ff41)" />
      <MetricRow label="Total" value={data.total ?? '—'} />
    </div>
  )
}
