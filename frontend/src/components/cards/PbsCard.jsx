import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function PbsCard({ data, config, trends }) {
  if (!data) return null
  const datastores = data.datastores || []
  return (
    <div>
      <MetricRow label="Tasks OK" value={data.tasks_ok ?? '—'} valueColor="var(--ok-color, #00ff41)" />
      <MetricRow label="Tasks Failed" value={data.tasks_fail ?? data.tasks_failed ?? 0} valueColor={(data.tasks_fail || data.tasks_failed) > 0 ? 'var(--error-color, #ff3333)' : undefined} />
      <MetricRow label="Running" value={data.tasks_running ?? 0} />
      <MetricRow label="Last Backup" value={data.last_backup || '—'} />
      {datastores.length > 0 && (
        <>
          <SectionHeader>Datastores</SectionHeader>
          {datastores.map((ds, i) => (
            <MetricRow
              key={i}
              label={ds.name || `DS ${i + 1}`}
              value={ds.used != null ? `${ds.used} / ${ds.total}` : ds.status || '—'}
            />
          ))}
        </>
      )}
    </div>
  )
}
