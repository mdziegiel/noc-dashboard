import React from 'react'
import { M, Sub, Spark, fmt } from '../shared.jsx'

export default function AdguardCard({ data, config }) {
  if (!data) return null
  const blockState = (data.block_pct ?? 0) > 40 ? 'warn' : ''
  const trends = data._trends
  return (
    <>
      <div className="card-b">
        <M v={fmt(data.queries)} l="Queries" />
        <M v={`${data.block_pct ?? 0}%`} l="Blocked" s={blockState} />
        {trends?.block_pct
          ? <Spark data={trends.block_pct} state={blockState || 'ok'} label={`blocked ${trends.block_pct.length}d trend`} />
          : <Spark label="blocked 1d trend" />
        }
      </div>
      <Sub>{data.blocked != null ? `${fmt(data.blocked)} blocked · ${data.avg_ms ?? '—'}ms avg` : null}</Sub>
    </>
  )
}
