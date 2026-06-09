import React from 'react'
import { MetricRow, SectionHeader, stateToColor } from '../shared.jsx'

export default function UrbackupCard({ data, config, trends }) {
  if (!data) return null
  const clients = data.clients || []
  return (
    <div>
      <MetricRow label="Online" value={`${data.online ?? '?'} / ${data.total ?? '?'}`} />
      {clients.length > 0 && (
        <>
          <SectionHeader>Clients</SectionHeader>
          {clients.map((c, i) => (
            <MetricRow
              key={i}
              label={c.name || `Client ${i + 1}`}
              value={c.status || c.state || '—'}
              valueColor={stateToColor(c.state)}
            />
          ))}
        </>
      )}
    </div>
  )
}
