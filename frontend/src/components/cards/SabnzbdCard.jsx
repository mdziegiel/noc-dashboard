import React from 'react'
import { MetricRow, Sparkline } from '../shared.jsx'

export default function SabnzbdCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: slots, speed_mbps, status, mbleft, timeleft, day_gb
  const speed = data.speed_mbps != null
    ? `${data.speed_mbps} MB/s`
    : data.speed || '—'
  const queue = data.slots ?? data.queue_slots ?? data.queue ?? '—'
  return (
    <div>
      <MetricRow
        label="Status"
        value={data.status ?? '—'}
        valueColor={data.status === 'Downloading' ? 'var(--ok-color, #00ff41)' : undefined}
      />
      <MetricRow label="Queue" value={queue} />
      <MetricRow
        label="Speed"
        value={speed}
        valueColor={data.speed_mbps > 0 ? 'var(--ok-color, #00ff41)' : undefined}
      />
      <MetricRow label="Today" value={data.day_gb != null ? `${data.day_gb} GB` : '—'} />
      {data.timeleft && <MetricRow label="ETA" value={data.timeleft} />}
      {trends?.speed && config?.graph !== false && (
        <Sparkline data={trends.speed} color={config?.graph_color} />
      )}
    </div>
  )
}
