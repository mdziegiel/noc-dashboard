import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function HypervCard({ data, config }) {
  if (!data) return null

  const vms = data.vms || []
  const running = data.running ?? 0
  const stopped = data.stopped ?? 0
  const total = data.vm_count ?? vms.length

  const vmStr = `${running}/${total}`
  const vmState = data.state === 'error' ? 'crit'
    : stopped > 0 ? 'warn'
    : total === 0 ? 'warn'
    : 'ok'

  const cpuVals = vms.map(v => v.cpu ?? 0).filter(n => n > 0)
  const avgCpu = cpuVals.length > 0
    ? (cpuVals.reduce((a, b) => a + b, 0) / cpuVals.length).toFixed(0)
    : '—'
  const cpuState = parseFloat(avgCpu) >= 90 ? 'crit'
    : parseFloat(avgCpu) >= 75 ? 'warn'
    : ''

  const memTotal = vms.reduce((s, v) => s + (v.mem_assigned ?? 0), 0)
  const memStr = memTotal > 0 ? `${memTotal.toFixed(1)} GB` : '—'

  const hostStr = data.host_cpus != null && data.host_mem_gb != null
    ? `${data.host_cpus} vCPU · ${data.host_mem_gb} GB`
    : '—'

  // Build sub text
  const subParts = []
  if (data.state === 'error') {
    subParts.push(data.note || 'host unreachable')
  } else if (stopped > 0) {
    const downNames = vms.filter(v => v.state !== 'Running').map(v => v.name).slice(0, 3)
    subParts.push(`OFF: ${downNames.join(', ')}`)
  } else if (total > 0) {
    subParts.push(`all VMs running`)
  }
  if (data.host_mem_gb && data.state !== 'error') {
    subParts.push(`host ${hostStr}`)
  }

  return (
    <>
      <div className="card-b">
        <M v={vmStr}         l="VMs"      s={vmState} />
        <M v={avgCpu !== '—' ? `${avgCpu}%` : '—'} l="CPU avg"  s={cpuState} />
        <M v={memStr}        l="RAM alloc" />
      </div>

      {vms.length > 0 && (
        <div className="card-b" style={{ marginTop: '4px' }}>
          {vms.slice(0, 4).map(vm => {
            const dot = vm.state === 'Running' ? 'ok'
              : vm.state === 'Off' ? 'crit'
              : 'warn'
            return (
              <div key={vm.name} className="metric" style={{ fontSize: '10px', padding: '1px 0' }}>
                <span className={`dot dot-${dot}`} style={{ width: 6, height: 6, minWidth: 6 }} />
                <span className="m-l" style={{ marginLeft: 4 }}>{vm.name}</span>
                {vm.state === 'Running' && vm.cpu > 0 && (
                  <span className="m-v" style={{ marginLeft: 'auto', opacity: 0.7 }}>
                    {vm.cpu.toFixed(0)}%
                  </span>
                )}
                {vm.state !== 'Running' && (
                  <span className="m-v" style={{ marginLeft: 'auto', opacity: 0.6 }}>
                    {vm.state}
                  </span>
                )}
              </div>
            )
          })}
          {vms.length > 4 && (
            <div style={{ fontSize: '10px', opacity: 0.5, paddingTop: 2 }}>
              +{vms.length - 4} more
            </div>
          )}
        </div>
      )}

      <Sub>{subParts.join(' · ') || null}</Sub>
    </>
  )
}
