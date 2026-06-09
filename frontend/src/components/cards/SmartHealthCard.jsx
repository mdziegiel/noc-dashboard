import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function SmartHealthCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: checked, passed, warn, fail, prefail, disks [{node, dev, model, health, issues}]
  const problems = data.problems || []
  const disks = data.disks || []
  return (
    <div>
      <MetricRow
        label="Passed"
        value={`${data.passed ?? '?'} / ${data.checked ?? data.total ?? '?'}`}
        valueColor={data.fail > 0 ? 'var(--error-color, #ff3333)' : 'var(--ok-color, #00ff41)'}
      />
      {data.warn > 0 && <MetricRow label="Warnings" value={data.warn} valueColor="var(--warn-color, #ffaa00)" />}
      {data.fail > 0 && <MetricRow label="Failed" value={data.fail} valueColor="var(--error-color, #ff3333)" />}
      {data.prefail > 0 && <MetricRow label="Pre-fail" value={data.prefail} valueColor="var(--warn-color, #ffaa00)" />}
      {problems.length > 0 && (
        <>
          <SectionHeader>Problems</SectionHeader>
          {problems.map((p, i) => (
            <div key={i} style={{ fontSize: 10, color: 'var(--error-color, #ff3333)', padding: '1px 0' }}>
              {typeof p === 'string' ? p : `${p.disk || p.device || ''}: ${p.issue || p.status || '?'}`}
            </div>
          ))}
        </>
      )}
      {disks.length > 0 && (
        <>
          <SectionHeader>Disks</SectionHeader>
          {disks.map((d, i) => (
            <MetricRow
              key={i}
              label={d.dev ? d.dev.replace('/dev/', '') : `Disk ${i + 1}`}
              value={d.health || '—'}
              valueColor={d.health === 'PASSED' ? 'var(--ok-color, #00ff41)' : 'var(--error-color, #ff3333)'}
            />
          ))}
        </>
      )}
    </div>
  )
}
