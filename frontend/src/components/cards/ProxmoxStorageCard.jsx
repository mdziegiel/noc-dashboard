import React from 'react'
import { M, Sub, Donut, fmt } from '../shared.jsx'

export default function ProxmoxStorageCard({ data, config }) {
  if (!data) return null
  const storages = data.storage || []
  return (
    <>
      <div className="card-b">
        {storages.length === 0 && <M v="—" l="Storage" />}
      </div>
      {storages.length > 0 && (
        <div className="gauges">
          {storages.map((s, i) => {
            const pct = s.pct ?? s.used_pct ?? 0
            const state = pct >= 90 ? 'crit' : pct >= 75 ? 'warn' : ''
            return <Donut key={i} label={s.name} pct={pct} state={state} />
          })}
        </div>
      )}
    </>
  )
}
