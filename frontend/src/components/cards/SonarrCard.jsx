import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function SonarrCard({ data, config }) {
  if (!data) return null
  const queueState = (data.queue || 0) > 0 ? 'warn' : ''
  const missingState = (data.missing || 0) > 0 ? 'warn' : ''
  return (
    <>
      <div className="card-b">
        <M v={fmt(data.monitored ?? data.total)} l="Monitored" />
        <M v={data.queue ?? 0} l="Queue" s={queueState} />
        <M v={data.missing ?? 0} l="Missing" s={missingState} />
      </div>
      <Sub>{fmt(data.total)} series total</Sub>
    </>
  )
}
