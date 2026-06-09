import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function HomeAssistantCard({ data, config }) {
  if (!data) return null
  const unavailState = (data.unavailable || 0) > 0 ? 'warn' : ''
  const alertsState = (data.alerts_on || 0) > 0 ? 'warn' : 'ok'
  const sub = `${data.domains ?? '?'} domains · ${data.notifications ?? 0} notification(s)`
  return (
    <>
      <div className="card-b">
        <M v={data.entities ?? '—'} l="Entities" />
        <M v={data.alerts_on ?? 0} l="Alerts" s={alertsState} />
        <M v={(data.unavailable ?? 0)} l="Unavail" s={unavailState} />
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
