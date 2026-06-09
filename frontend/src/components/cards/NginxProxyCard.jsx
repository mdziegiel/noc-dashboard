import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function NginxProxyCard({ data, config, trends }) {
  if (!data) return null
  const expiring = data.expiring_certs || []
  return (
    <div>
      <MetricRow label="Enabled Hosts" value={data.enabled_hosts ?? data.hosts ?? '—'} />
      <MetricRow label="Certs" value={data.cert_count ?? data.certs ?? '—'} />
      {expiring.length > 0 && (
        <>
          <SectionHeader>Expiring Certs</SectionHeader>
          {expiring.map((c, i) => (
            <MetricRow
              key={i}
              label={c.domain || c.name || `cert ${i + 1}`}
              value={c.days_left != null ? `${c.days_left}d` : c.expiry || '—'}
              valueColor="var(--warn-color, #ffaa00)"
            />
          ))}
        </>
      )}
    </div>
  )
}
