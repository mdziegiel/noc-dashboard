import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function SabnzbdCard({ data, config }) {
  if (!data) return null
  const queueState = (data.slots || 0) > 0 ? 'warn' : 'ok'
  const sub = `status ${data.status || 'Idle'}${data.slots > 0 && data.timeleft ? ` · ${data.timeleft} left` : ''}`
  return (
    <>
      <div className="card-b">
        <M v={data.slots ?? 0} l="Queue" s={queueState} />
        <M v={data.speed_mbps != null ? `${data.speed_mbps} MB/s` : '—'} l="Speed" />
        <M v={data.day_gb != null ? `${data.day_gb} GB` : '—'} l="Today" />
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
