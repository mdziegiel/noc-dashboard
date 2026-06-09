import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function UptimeKumaCard({ data, config }) {
  if (!data) return null
  const down = data.down || []
  const allUp = data.up === data.total && down.length === 0
  const sub = allUp ? 'all monitors up' : down.length > 0 ? `down: ${down.slice(0,3).join(', ')}` : null
  return (
    <>
      <div className="card-b">
        <M v={`${data.up ?? '?'}/${data.total ?? '?'} up`} l="Monitors" s={allUp ? 'ok' : down.length > 0 ? 'crit' : 'warn'} />
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
