import React from 'react'
import { M, Sub, Spark, fmt } from '../shared.jsx'

export default function UnifiCard({ data, config }) {
  if (!data) return null
  // wan_health and unifi share same collector
  const wan = data.wan === 'ok' || data.wan_status === 'up' ? 'OK' : (data.wan || data.wan_status || '?').toUpperCase()
  const wanState = (data.wan === 'ok' || data.wan_status === 'up') ? 'ok' : 'crit'
  const ssids = data.ssids || []
  const devices = data.devices || []
  const pia = data.pia || {}
  const monthRx = data.month_rx, monthTx = data.month_tx

  // Format monthly data like the generator: "1019G↓ / 337G↑"
  function fmtG(b) {
    if (!b) return null
    const g = b / 1e9
    return g >= 1 ? `${Math.round(g)}G` : `${(g*1000).toFixed(0)}M`
  }
  const monthly = (monthRx && monthTx) ? `${fmtG(monthRx)}↓ / ${fmtG(monthTx)}↑` : null
  const sub = data.wan_ip ? `${data.wan_ip}` : null

  const ipsState = (data.ips_24h || 0) > 0 ? 'warn' : ''

  return (
    <>
      <div className="card-b">
        <M v={wan} l="WAN" s={wanState} />
        <M v={data.clients ?? data.client_count ?? '—'} l="Clients" />
        <M v={(data.ips_24h ?? 0)} l="IPS 24h" s={ipsState} />
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
      {sub && <Sub>{sub}{data.latency != null ? ` · ${data.latency}ms latency` : ''}</Sub>}
    </>
  )
}
