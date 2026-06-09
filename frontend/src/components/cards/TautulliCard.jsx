import React from 'react'
import { MetricRow } from '../shared.jsx'

export default function TautulliCard({ data, config, trends }) {
  if (!data) return null
  return (
    <div>
      <MetricRow label="Streams" value={data.streams ?? data.active_streams ?? '—'} />
      <MetricRow label="Plays Today" value={data.plays_today ?? '—'} />
      <MetricRow label="Top User" value={data.top_user ?? '—'} />
    </div>
  )
}
