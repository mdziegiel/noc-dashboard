import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function DockerCard({ data, config }) {
  if (!data) return null
  const bad = data.bad || data.bad_containers || []
  const runState = bad.length > 0 ? 'warn' : 'ok'
  return (
    <>
      <div className="card-b">
        <M v={`${data.running ?? '?'}/${data.total ?? '?'}`} l="Running" s={runState} />
        <M v={data.envs ?? data.env_count ?? '—'} l="Envs" />
      </div>
      <Sub>{bad.length > 0 ? `down ${bad.slice(0,3).join(', ')}` : null}</Sub>
    </>
  )
}
