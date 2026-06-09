import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function CustomUrlCard({ data, config }) {
  if (!data) return null
  const values = data.values || {}
  const entries = Object.entries(values)
  return (
    <>
      <div className="card-b">
        {entries.slice(0,6).map(([k, v]) => (
          <M key={k} v={typeof v === 'object' ? JSON.stringify(v) : String(v)} l={k} />
        ))}
        {entries.length === 0 && <M v="—" l="no data" />}
      </div>
    </>
  )
}
