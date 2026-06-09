import React from 'react'
import { MetricRow, SectionHeader, DonutGauge } from '../shared.jsx'

export default function PbsCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: ok, fail, run, last_backup, datastores [{name, pct}]
  const datastores = data.datastores || []
  const tasksFail = data.fail ?? data.tasks_fail ?? data.tasks_failed ?? 0
  const tasksOk = data.ok ?? data.tasks_ok ?? 0
  const tasksRun = data.run ?? data.tasks_running ?? 0
  return (
    <div>
      <MetricRow
        label="Tasks OK"
        value={tasksOk}
        valueColor="var(--ok-color, #00ff41)"
      />
      <MetricRow
        label="Tasks Failed"
        value={tasksFail}
        valueColor={tasksFail > 0 ? 'var(--error-color, #ff3333)' : undefined}
      />
      <MetricRow label="Running" value={tasksRun} />
      <MetricRow label="Last Backup" value={data.last_backup || '—'} />
      {datastores.length > 0 && (
        <>
          <SectionHeader>Datastores</SectionHeader>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
            {datastores.map((ds, i) => (
              <DonutGauge
                key={ds.name || i}
                value={ds.pct ?? ds.used_pct ?? 0}
                max={100}
                color={ds.pct > 85 ? 'var(--warn-color, #ffaa00)' : 'var(--gauge-fill-ok, #00ff41)'}
                label={ds.name || `DS ${i + 1}`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
