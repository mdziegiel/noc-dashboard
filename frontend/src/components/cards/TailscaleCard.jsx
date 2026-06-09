import React from 'react'
import { M, Sub, fmt } from '../shared.jsx'

export default function TailscaleCard({ data, config }) {
  if (!data) return null
  const devices = data.devices || []
  const expiryState = (data.soonest_expiry_days ?? 999) < 0 ? 'crit' : (data.soonest_expiry_days ?? 999) < 30 ? 'warn' : ''
  const expiryStr = data.soonest_expiry_days != null
    ? (data.soonest_expiry_days < 0 ? `key expired ${Math.abs(data.soonest_expiry_days)}d ago` : `key expires ${data.soonest_expiry_days}d`)
    : null
  return (
    <>
      <div className="card-b">
        <M v={data.total ?? '—'} l="Devices" />
        <M v={data.online ?? '—'} l="Online" s={data.online > 0 ? 'ok' : ''} />
        <M v={data.offline ?? 0} l="Offline" s={(data.offline ?? 0) > 0 ? 'warn' : ''} />
        {devices.length > 0 && (
          <div className="ublist">
            {devices.slice(0, 6).map((d, i) => (
              <div key={i} className={`ubrow`}>
                <span className="ub-n">{d.name}</span>
                <span className="ub-a" style={{ color: d.online ? 'var(--green)' : 'var(--muted)' }}>{d.online ? 'online' : 'offline'}</span>
              </div>
            ))}
          </div>
        )}
        {expiryStr && <M v={expiryStr} l="Key" s={expiryState} />}
      </div>
      <Sub>{data.online != null ? `${data.online} online · key expires ${data.soonest_expiry_days ?? '?'}d` : null}</Sub>
    </>
  )
}
