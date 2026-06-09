import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function ProxmoxCard({ data, config }) {
  if (!data) return null
  const downVms = data.down_vms || []
  const cpuPct = data.cpu != null ? data.cpu : (data.cpu_pct ?? null)
  const cpuState = cpuPct != null ? (cpuPct >= 90 ? 'crit' : cpuPct >= 75 ? 'warn' : '') : ''
  const memUsed = data.mem_used ?? data.ram_gb ?? null
  const memTotal = data.mem_total ?? data.ram_total ?? null
  const vmsState = downVms.length > 0 ? 'crit' : 'ok'

  const vmsStr = `${data.vms_running ?? data.cpu != null ? (data.vms_running ?? '?') : '?'}/${data.vms_total ?? '?'}`
  const cpuStr = cpuPct != null ? `${cpuPct}%` : '—'
  const ramStr = (memUsed != null && memTotal != null) ? `${memUsed}/${memTotal}G` : '—'
  const uptimeStr = data.uptime_d != null ? `${data.uptime_d}d` : (data.uptime_days != null ? `${data.uptime_days}d` : null)

  const subParts = []
  if (downVms.length > 0) subParts.push(`DOWN: ${downVms.join(', ')}`)
  if (uptimeStr) subParts.push(`uptime ${uptimeStr}`)

  return (
    <>
      <div className="card-b">
        <M v={vmsStr} l="VMs" s={vmsState} />
        <M v={cpuStr} l="CPU" s={cpuState} />
        <M v={ramStr} l="RAM" />
      </div>
      <Sub>{subParts.join(' · ') || null}</Sub>
    </>
  )
}
