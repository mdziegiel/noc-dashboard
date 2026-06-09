import React from 'react'
import { Donut } from '../shared.jsx'

export default function ProxmoxStorageCard({ data, config }) {
  if (!data) return null
  const storages = data.storage || []
  if (storages.length === 0) {
    return <div className="card-b"><div className="metric"><div className="m-v">—</div><div className="m-l">Storage</div></div></div>
  }
  return (
    <div className="gauges">
      {storages.map((s, i) => {
        const pct = s.pct ?? s.used_pct ?? 0
        const state = pct >= 90 ? 'crit' : pct >= 80 ? 'warn' : 'ok'
        return <Donut key={i} label={s.name} pct={pct} state={state} />
      })}
    </div>
  )
}
