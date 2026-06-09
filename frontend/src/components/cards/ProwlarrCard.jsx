import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function ProwlarrCard({ data, config, trends }) {
  if (!data) return null
  const failing = data.failing_indexers || []
  return (
    <div>
      <MetricRow label="Indexers" value={`${data.healthy ?? '?'} / ${data.enabled ?? data.total ?? '?'} healthy`} />
      {failing.length > 0 && (
        <>
          <SectionHeader>Failing</SectionHeader>
          {failing.map((idx, i) => (
            <div key={i} style={{ fontSize: 10, color: 'var(--error-color, #ff3333)', padding: '1px 0' }}>
              {typeof idx === 'string' ? idx : idx.name || `Indexer ${i + 1}`}
            </div>
          ))}
        </>
      )}
    </div>
  )
}
