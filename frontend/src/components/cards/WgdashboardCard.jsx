import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function WgdashboardCard({ data, config }) {
  if (!data) return null

  const ifaces = data.interfaces || []
  const up = data.ifaces_up ?? 0
  const total = data.ifaces_total ?? ifaces.length
  const connected = data.connected ?? 0
  const peers = data.total_peers ?? 0

  const ifaceState = data.state === 'error' ? 'crit'
    : up < total ? 'warn'
    : total > 0 ? 'ok' : ''

  return (
    <>
      <div className="card-b">
        <M v={`${up}/${total}`} l="Interfaces" s={ifaceState} />
        <M v={connected} l="Connected" />
        <M v={peers} l="Total Peers" />
      </div>
      {ifaces.length > 0 && ifaces.map(iface => (
        <div key={iface.name} style={{ fontSize: 10, padding: '1px 0', display: 'flex', alignItems: 'center', gap: 4 }}>
          <span className={`dot ${iface.up ? 'dot-ok' : 'dot-crit'}`} style={{ width: 6, height: 6, minWidth: 6 }} />
          <span style={{ opacity: 0.9 }}>{iface.name}</span>
          <span style={{ marginLeft: 'auto', opacity: 0.65 }}>{iface.connected}/{iface.total}</span>
        </div>
      ))}
      <Sub>{data.note || (total > 0 ? `${up}/${total} interfaces up · ${connected} peers connected` : null)}</Sub>
    </>
  )
}
