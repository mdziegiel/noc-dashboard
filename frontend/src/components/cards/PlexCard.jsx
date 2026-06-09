import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function PlexCard({ data, config }) {
  if (!data) return null
  const streamState = (data.streams || 0) > 0 ? 'warn' : 'ok'
  return (
    <>
      <div className="card-b">
        <M v={data.streams ?? 0} l="Streams" s={streamState} />
        <M v={fmt(data.movies)} l="Movies" />
        <M v={fmt(data.shows)} l="Shows" />
      </div>
      <Sub>{data.streams > 0 ? `${data.streams} active stream(s)` : 'library idle'}</Sub>
    </>
  )
}
