import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function GenericCard({ data, config }) {
  if (!data) return null
  const entries = Object.entries(data).filter(([k, v]) => !k.startsWith('_') && k !== 'state' && typeof v !== 'object')
  return (
    <>
      <div className="card-b">
        {entries.slice(0, 6).map(([k, v]) => (
          <M key={k} v={String(v)} l={k.replace(/_/g,' ')} />
        ))}
        {entries.length === 0 && <M v="—" l="no data" />}
      </div>
    </>
  )
}
