import React from 'react'
import { M, Sub, Spark, fmt } from '../shared.jsx'

export default function NginxProxyCard({ data, config }) {
  if (!data) return null
  const certList = data.cert_list || []
  const sub = data.errored > 0 ? `${data.errored} errored` : 'all hosts enabled — no errors'
  return (
    <>
      <div className="card-b">
        <M v={data.hosts ?? data.enabled ?? '—'} l="Proxy Hosts" />
        <M v={data.enabled ?? '—'} l="Enabled" s={data.enabled > 0 ? 'ok' : ''} />
        <M v={data.disabled ?? 0} l="Disabled" />
        <M v={data.errored ?? 0} l="Errored" s={data.errored > 0 ? 'warn' : ''} />
        <M v={data.certs ?? data.cert_count ?? '—'} l="SSL Certs" />
        {certList.length > 0 && (
          <div className="ublist">
            {certList.slice(0, 8).map((c, i) => (
              <div key={i} className="ubrow">
                <span className="ub-n">{c.name || c.domain}</span>
                <span className="ub-a">{c.days != null ? `${c.days}d` : ''}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <Sub>{sub}</Sub>
    </>
  )
}
