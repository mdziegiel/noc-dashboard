import React from 'react'
import { MetricRow } from '../shared.jsx'

export default function CustomUrlCard({ data, config, trends }) {
  if (!data) return null
  const values = data.values || {}
  return (
    <div>
      {Object.entries(values).map(([k, v]) => (
        <MetricRow key={k} label={k} value={typeof v === 'object' ? JSON.stringify(v) : String(v)} />
      ))}
      {!Object.keys(values).length && (
        <div style={{ fontSize: 11, color: 'var(--text-muted, #555)' }}>No data</div>
      )}
    </div>
  )
}
