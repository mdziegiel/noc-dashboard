import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function PbsCard({ data, config }) {
  if (!data) return null
  const failState = (data.fail || 0) > 0 ? 'crit' : ''
  const lastBackupState = data.state === 'crit' ? 'crit' : ''
  const datastores = data.datastores || []
  const sub = [
    data.fail > 0 ? `${data.fail} FAILED task(s) in 24h` : null,
    ...datastores.map(d => `datastore ${d.name}: ${Math.round(d.pct)}% used`)
  ].filter(Boolean).join(' · ')
  return (
    <>
      <div className="card-b">
        <M v={data.last_backup || '—'} l="Last Backup" s={lastBackupState} />
        <M v={`${data.ok ?? 0} ok / ${data.fail ?? 0} fail`} l="24h Tasks" s={failState} />
      </div>
      <Sub>{sub || null}</Sub>
    </>
  )
}
