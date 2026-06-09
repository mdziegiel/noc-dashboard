import React from 'react'
import { M, Sub, Spark, fmt } from '../shared.jsx'

// Shared component — called from both UnifiCard and WanHealthCard
// mode='wan': WAN / INTERNET card (latency-focused, like generate_dashboard.py wan_body)
// mode='unifi': UNIFI UDM-SE card (clients, SSIDs, devices, monthly)
function UnifiInner({ data, mode }) {
  if (!data) return null
  const wan = data.wan === 'ok' || data.wan_status === 'up' ? 'OK' : (data.wan || '?').toUpperCase()
  const wanState = (data.wan === 'ok' || data.wan_status === 'up') ? 'ok' : 'crit'
  const ssids = data.ssids || []
  const devices = data.devices || []
  const pia = data.pia || {}
  const monthRx = data.month_rx, monthTx = data.month_tx

  function fmtG(b) {
    if (!b) return null
    const g = b / 1e9
    return g >= 1 ? `${Math.round(g)}G` : `${(g*1000).toFixed(0)}M`
  }

  if (mode === 'wan') {
    // WAN / INTERNET card — matches generator wan_body
    const trends = data._trends
    return (
      <>
        <div className="card-b">
          <M v={wan} l="WAN" s={wanState} />
          <M v={data.latency != null ? `${data.latency}ms` : '—'} l="Latency" />
          <M v={data.down_mbps != null && data.up_mbps != null && (data.down_mbps || data.up_mbps) ? `${data.down_mbps}↓/${data.up_mbps}↑` : 'n/a'} l="Speedtest" />
          {trends?.latency
            ? <Spark data={trends.latency} state="ok" label={`latency ${trends.latency.length} samples / 24h`} />
            : <Spark label={`latency 1 samples / 24h`} />
          }
        </div>
        <Sub>{data.wan_ip ? `${data.wan_ip} · down/up Mbps from UniFi speedtest history` : null}</Sub>
      </>
    )
  }

  // UNIFI UDM-SE card — matches generator uni_body
  const monthly = (monthRx && monthTx) ? `${fmtG(monthRx)}↓ / ${fmtG(monthTx)}↑` : null
  const ipsState = (data.ips_24h || 0) > 0 ? 'warn' : ''
  return (
    <>
      <div className="card-b">
        <M v={wan} l="WAN" s={wanState} />
        <M v={data.clients ?? '—'} l="Clients" />
        <M v={data.ips_24h ?? 0} l="IPS 24h" s={ipsState} />
        {ssids.length > 0 && (
          <div className="ublist">
            {ssids.map((s, i) => (
              <div key={i} className="ubrow">
                <span className="ub-n">{s.name || s}</span>
                <span className="ub-a">{s.clients != null ? `${s.clients} clients` : ''}</span>
              </div>
            ))}
          </div>
        )}
        {monthly && (
          <div className="ublist">
            <div className="ubrow">
              <span className="ub-n">Mo. Data</span>
              <span className="ub-a">{monthly}</span>
            </div>
            {pia.name && (
              <div className="ubrow">
                <span className="ub-n">VPN {pia.name}</span>
                <span className="ub-a">{pia.status || (pia.connected ? 'VALID' : 'INVALID')}</span>
              </div>
            )}
          </div>
        )}
        {devices.length > 0 && (
          <div className="dvlist">
            {devices.map((d, i) => (
              <div key={i} className={`dv dv-${d.online ? 'on' : 'off'}`}>
                <span className="dv-dot" />
                <span className="dv-name">{d.name}</span>
                <span className="dv-kind">{d.kind}</span>
                <span className="dv-up">{d.uptime}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <Sub>{data.wan_ip ? `${data.wan_ip} · ${data.latency != null ? `${data.latency}ms latency` : ''}` : null}</Sub>
    </>
  )
}

export default function UnifiCard({ data, config }) {
  // Default export = UNIFI UDM-SE mode
  return <UnifiInner data={data} mode="unifi" />
}

// Named export for WAN / INTERNET card
export function WanHealthCard({ data, config }) {
  return <UnifiInner data={data} mode="wan" />
}
