import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function ProwlarrCard({ data, config }) {
  if (!data) return null
  const failingState = (data.failing || 0) > 0 ? 'crit' : ''
  return (
    <>
      <div className="card-b">
        <M v={data.total ?? '—'} l="Indexers" />
        <M v={data.healthy ?? 0} l="Healthy" s={data.healthy > 0 ? 'ok' : ''} />
        <M v={data.failing ?? 0} l="Failing" s={failingState} />
      </div>
      <Sub>{(data.enabled ?? data.total) != null ? `${data.enabled ?? data.total}/${data.total ?? '?'} enabled` : null}</Sub>
    </>
  )
}
