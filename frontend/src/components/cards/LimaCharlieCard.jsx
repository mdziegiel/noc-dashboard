import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function LimaCharlieCard({ data, config }) {
  if (!data) return null
  const top = data.top || []
  const detState = (data.detections_24h || 0) > 0 ? 'warn' : ''
  const sub = top.length > 0 ? `top: ${top.slice(0,2).map(([k,v]) => `${k}(${v})`).join(', ')}` : null
  return (
    <>
      <div className="card-b">
        <M v={`${data.online ?? '?'}/${data.total ?? '?'} online`} l="Sensors" s={(data.offline ?? 0) === 0 ? 'ok' : ''} />
        <M v={data.offline ?? 0} l="Offline" />
        <M v={fmt(data.detections_24h ?? 0)} l="Detections 24h" s={detState} />
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
