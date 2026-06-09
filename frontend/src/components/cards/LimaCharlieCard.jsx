import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function LimaCharlieCard({ data, config, trends }) {
  if (!data) return null
  const offline = data.offline_hosts || []
  return (
    <div>
      <MetricRow label="Sensors" value={`${data.online ?? data.sensors_online ?? '?'} / ${data.total ?? data.sensors_total ?? '?'}`} />
      <MetricRow label="Detections 24h" value={data.detections_24h ?? 0} valueColor={data.detections_24h > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      {offline.length > 0 && (
        <>
          <SectionHeader>Offline Hosts</SectionHeader>
          {offline.map((h, i) => (
            <div key={i} style={{ fontSize: 10, color: 'var(--text-muted, #555)', padding: '1px 0' }}>
              {typeof h === 'string' ? h : h.name || h.hostname || `Host ${i + 1}`}
            </div>
          ))}
        </>
      )}
    </div>
  )
}
