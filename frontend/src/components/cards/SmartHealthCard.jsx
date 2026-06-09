import React from 'react'
import { MetricRow, SectionHeader } from '../shared.jsx'

export default function SmartHealthCard({ data, config, trends }) {
  if (!data) return null
  const problems = data.problems || []
  return (
    <div>
      <MetricRow label="Passed" value={`${data.passed ?? '?'} / ${data.checked ?? data.total ?? '?'}`} valueColor="var(--ok-color, #00ff41)" />
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
    </div>
  )
}
