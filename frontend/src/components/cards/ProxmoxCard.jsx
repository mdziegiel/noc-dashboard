import React from 'react'
import { MetricRow, SectionHeader, DonutGauge, Sparkline, stateToColor } from '../shared.jsx'

export default function ProxmoxCard({ data, config, trends }) {
  if (!data) return null
  const vms = data.vms || {}
  const nodes = data.nodes || {}
  const storage = data.storage || {}

  const nodeList = Object.entries(nodes)
  const storageList = Object.entries(storage)
  const downVMs = data.down_vms || []

  return (
    <div>
      <MetricRow label="VMs Running" value={`${data.vms_running ?? '?'} / ${data.vms_total ?? '?'}`} />
      <MetricRow label="CPU" value={data.cpu_pct != null ? `${data.cpu_pct}%` : '—'} valueColor={data.cpu_pct > 80 ? 'var(--warn-color, #ffaa00)' : undefined} />
      <MetricRow label="RAM" value={data.ram_gb != null ? `${data.ram_gb} GB (${data.ram_pct}%)` : '—'} />
      <MetricRow label="Uptime" value={data.uptime_days != null ? `${data.uptime_days}d` : '—'} />
      {trends?.cpu && config?.graph !== false && (
        <Sparkline data={trends.cpu} color={config?.graph_color} />
      )}
      {storageList.length > 0 && (
        <>
          <SectionHeader>Storage</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 4 }}>
            {storageList.map(([name, s]) => (
              <DonutGauge
                key={name}
                value={s.used_pct ?? s.pct ?? 0}
                max={100}
                color={s.used_pct > 85 ? 'var(--warn-color, #ffaa00)' : 'var(--gauge-fill-ok, #00ff41)'}
                label={name}
              />
            ))}
          </div>
        </>
      )}
      {downVMs.length > 0 && (
        <>
          <SectionHeader>Down VMs</SectionHeader>
          {downVMs.map(vm => (
            <div key={vm} style={{ fontSize: 10, color: 'var(--error-color, #ff3333)', padding: '1px 0' }}>{vm}</div>
          ))}
        </>
      )}
    </div>
  )
}
