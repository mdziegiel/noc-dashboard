import React from 'react'
import { M, Sub, Spark, fmt } from '../shared.jsx'

export default function CrowdsecCard({ data, config }) {
  if (!data) return null
  const top = data.top || []
  const sub = top.length > 0 ? `top: ${top.slice(0,3).map(([k,v]) => `${k}(${v})`).join(', ')}` : 'no behavioral bans'
  const trends = data._trends
  return (
    <>
      <div className="card-b">
        <M v={fmt(data.bans)} l="Active Bans" />
        <M v={data.local_bans ?? 0} l="Local Bans" />
        <M v={data.detections_24h ?? '—'} l="Detections 24h" />
        {trends?.bans && <Spark data={trends.bans} state="crit" label={`bans ${trends.bans.length}d trend`} />}
        {!trends?.bans && <Spark label={`bans 1d trend`} />}
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
