import React from 'react'
import { MetricRow, SectionHeader, DonutGauge, Sparkline, stateToColor } from '../shared.jsx'

export default function ProxmoxCard({ data, config, trends }) {
  if (!data) return null
  const downVMs = data.down_vms || []
  const storage = Array.isArray(data.storage) ? data.storage : []

  // Collector returns: vms_running, vms_total, cpu (%), mem_used (GB), mem_total (GB), uptime_d
  const cpu = data.cpu ?? data.cpu_pct
  const memUsed = data.mem_used ?? data.ram_gb
  const memTotal = data.mem_total
  const memPct = memTotal ? Math.round(memUsed / memTotal * 100) : null

  return (
    <div>
      <MetricRow
        label="VMs"
        value={`${data.vms_running ?? '?'} / ${data.vms_total ?? '?'}`}
        valueColor={downVMs.length > 0 ? 'var(--warn-color, #ffaa00)' : 'var(--ok-color, #00ff41)'}
      />
      <MetricRow
        label="CPU"
        value={cpu != null ? `${cpu}%` : '—'}
        valueColor={cpu > 80 ? 'var(--error-color, #ff3333)' : cpu > 60 ? 'var(--warn-color, #ffaa00)' : 'var(--ok-color, #00ff41)'}
      />
      <MetricRow
        label="RAM"
        value={memUsed != null ? (memTotal ? `${memUsed}G / ${memTotal}G (${memPct}%)` : `${memUsed} GB`) : '—'}
        valueColor={memPct > 85 ? 'var(--warn-color, #ffaa00)' : undefined}
      />
      <MetricRow label="Uptime" value={data.uptime_d != null ? `${data.uptime_d}d` : '—'} />
      {trends?.cpu && config?.graph !== false && (
        <Sparkline data={trends.cpu} color={config?.graph_color} />
      )}
      {storage.length > 0 && (
        <>
          <SectionHeader>Storage</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
            {storage.map((s, i) => (
              <DonutGauge
                key={s.name || i}
                value={s.pct ?? 0}
                max={100}
                color={s.pct > 85 ? 'var(--warn-color, #ffaa00)' : 'var(--gauge-fill-ok, #00ff41)'}
                label={s.name}
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
