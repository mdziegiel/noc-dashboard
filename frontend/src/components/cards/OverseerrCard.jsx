import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function OverseerrCard({ data, config }) {
  if (!data) return null
  const pendingState = (data.pending || 0) > 0 ? 'warn' : 'ok'
  return (
    <>
      <div className="card-b">
        <M v={data.pending ?? 0} l="Pending" s={pendingState} />
        <M v={fmt(data.approved)} l="Approved" />
        <M v={fmt(data.available)} l="Available" />
      </div>
      <Sub>{fmt(data.total)} total request(s)</Sub>
    </>
  )
}
