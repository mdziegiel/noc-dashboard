import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function UnifiCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: wan (ok/down), wan_ip, clients, ips_24h, latency, down_mbps, up_mbps, devices[]
  const devices = data.devices || []
  const wanStatus = data.wan || data.wan_status || '—'
  const throughput = (data.down_mbps != null && data.up_mbps != null)
    ? `↓${data.down_mbps} ↑${data.up_mbps} Mbps`
    : data.throughput || '—'

  return (
    <div>
      <MetricRow
        label="WAN"
        value={wanStatus.toUpperCase()}
        valueColor={wanStatus === 'ok' ? 'var(--ok-color, #00ff41)' : 'var(--error-color, #ff3333)'}
      />
      {data.wan_ip && <MetricRow label="WAN IP" value={data.wan_ip} />}
      <MetricRow label="Clients" value={data.clients ?? '—'} />
      <MetricRow label="Latency" value={data.latency != null ? `${data.latency}ms` : '—'} />
      <MetricRow label="Throughput" value={throughput} />
      <MetricRow
        label="IPS Alerts"
        value={data.ips_24h ?? data.ips_alerts ?? 0}
        valueColor={(data.ips_24h || data.ips_alerts) > 0 ? 'var(--warn-color, #ffaa00)' : undefined}
      />
      {devices.length > 0 && (
        <>
          <SectionHeader>Devices</SectionHeader>
          {devices.slice(0, 6).map((d, i) => (
            <MetricRow
              key={i}
              label={d.name || d.mac || `Device ${i + 1}`}
              value={d.kind ? `${d.kind} · ${d.uptime || '—'}` : (d.status || d.state || '—')}
              valueColor={d.online === false ? 'var(--text-muted, #555)' : undefined}
            />
          ))}
          {devices.length > 6 && <div style={{ fontSize: 10, color: 'var(--text-muted, #555)' }}>+{devices.length - 6} more</div>}
        </>
      )}
    </div>
  )
}
