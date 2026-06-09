import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function SmartHealthCard({ data, config }) {
  if (!data) return null
  const disks = data.disks || []
  const failState = data.fail > 0 ? 'crit' : data.warn > 0 ? 'warn' : ''
  const passed = `${data.passed ?? data.checked ?? '?'}/${data.checked ?? '?'} pass`
  return (
    <>
      <div className="card-b">
        <M v={passed} l="Host Disks" s={data.fail > 0 ? 'crit' : data.warn > 0 ? 'warn' : 'ok'} />
        <M v={data.prefail ?? 0} l="Problems" s={data.prefail > 0 ? 'warn' : ''} />
        <M v={data.vm_disks != null ? `${data.vm_disks}` : 'n/a'} l="VM SMART" />
      </div>
    </>
  )
}
