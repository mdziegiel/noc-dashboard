import React from 'react'
import { MetricRow } from '../shared.jsx'

export default function PlexCard({ data, config, trends }) {
  if (!data) return null
  return (
    <div>
      <MetricRow label="Active Streams" value={data.active_streams ?? data.streams ?? '—'} valueColor={data.active_streams > 0 ? 'var(--ok-color, #00ff41)' : undefined} />
      <MetricRow label="Movies" value={data.movies ?? '—'} />
      <MetricRow label="Shows" value={data.shows ?? data.tv_shows ?? '—'} />
      {data.version && <MetricRow label="Version" value={data.version} />}
    </div>
  )
}
