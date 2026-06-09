import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function UnifiCard({ data, config, trends }) {
  if (!data) return null
  const ssids = data.ssids || []
  const devices = data.devices || []
  return (
    <div>
      <MetricRow label="WAN" value={data.wan_status || data.wan || '—'} valueColor={data.wan_status === 'up' ? 'var(--ok-color, #00ff41)' : undefined} />
      <MetricRow label="Clients" value={data.clients ?? '—'} />
      <MetricRow label="Latency" value={data.latency != null ? `${data.latency}ms` : '—'} />
      <MetricRow label="Throughput" value={data.throughput || '—'} />
      <MetricRow label="IPS Alerts" value={data.ips_alerts ?? 0} valueColor={data.ips_alerts > 0 ? 'var(--warn-color, #ffaa00)' : undefined} />
      {data.pia_vpn != null && <MetricRow label="PIA VPN" value={data.pia_vpn ? 'Connected' : 'Down'} valueColor={data.pia_vpn ? 'var(--ok-color, #00ff41)' : 'var(--error-color, #ff3333)'} />}
      {ssids.length > 0 && (
        <>
          <SectionHeader>SSIDs</SectionHeader>
          {ssids.map((s, i) => (
            <MetricRow key={i} label={typeof s === 'string' ? s : s.name || `SSID ${i + 1}`} value={typeof s === 'object' ? s.clients ?? '—' : undefined} />
          ))}
        </>
      )}
      {devices.length > 0 && (
        <>
          <SectionHeader>Devices</SectionHeader>
          {devices.slice(0, 5).map((d, i) => (
            <MetricRow key={i} label={d.name || d.mac || `Device ${i + 1}`} value={d.status || d.state || '—'} />
          ))}
          {devices.length > 5 && <div style={{ fontSize: 10, color: 'var(--text-muted, #555)' }}>+{devices.length - 5} more</div>}
        </>
      )}
    </div>
  )
}
