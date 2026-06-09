import React from 'react'
import { MetricRow } from '../shared.jsx'

const SKIP = new Set(['state', '_trends', '_error'])

export default function GenericCard({ data, config, trends }) {
  if (!data) return null
  const entries = Object.entries(data).filter(([k, v]) => {
    if (SKIP.has(k)) return false
    if (typeof v === 'object' && v !== null) return false
    return true
  })
  return (
    <div>
      {entries.map(([k, v]) => (
        <MetricRow key={k} label={k.replace(/_/g, ' ')} value={String(v)} />
      ))}
      {entries.length === 0 && (
        <div style={{ fontSize: 11, color: 'var(--text-muted, #555)' }}>No display data</div>
      )}
    </div>
  )
}
