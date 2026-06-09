import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function HomeAssistantCard({ data, config, trends }) {
  if (!data) return null
  return (
    <div>
      <MetricRow label="Entities" value={data.entities ?? data.entity_count ?? '—'} />
      <MetricRow label="Alerts" value={data.alerts ?? 0} valueColor={data.alerts > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      <MetricRow label="Notifications" value={data.notifications ?? 0} />
      <MetricRow label="Unavailable" value={data.unavailable ?? data.unavailable_count ?? 0} valueColor={(data.unavailable || data.unavailable_count) > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      {data.version && <MetricRow label="Version" value={data.version} />}
    </div>
  )
}
