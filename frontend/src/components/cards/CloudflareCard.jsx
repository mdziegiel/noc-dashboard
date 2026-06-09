import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function CloudflareCard({ data, config }) {
  if (!data) return null
  const threatState = (data.threats || 0) > 0 ? 'warn' : ''
  function fmtBytes(b) {
    if (!b) return '—'
    if (b >= 1e9) return `${(b/1e9).toFixed(2)}GB`
    return `${(b/1e6).toFixed(1)}MB`
  }
  const sub = data.waf_note ? `WAF: ${data.waf_note.slice(0,60)}` : null
  return (
    <>
      <div className="card-b">
        <M v={fmt(data.requests)} l="Requests" />
        <M v={fmt(data.threats)} l="Threats" s={threatState} />
        <M v={fmtBytes(data.bytes)} l="Bandwidth" />
        {data.waf_events != null && <M v={fmt(data.waf_events)} l="WAF Events" s={data.waf_events > 0 ? 'warn' : ''} />}
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
