import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function TautulliCard({ data, config }) {
  if (!data) return null
  const streamState = (data.streams || 0) > 0 ? 'warn' : 'ok'
  const sub = data.top_user ? `top user: ${data.top_user} (${data.top_plays ?? '?'} plays)` : data.note || 'no plays today'
  return (
    <>
      <div className="card-b">
        <M v={data.plays_today ?? 0} l="Plays Today" />
        <M v={data.streams ?? 0} l="Streaming" s={streamState} />
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
