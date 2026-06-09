import React from 'react'
import { SectionHeader, DonutGauge, MetricRow } from '../shared.jsx'

export default function ProxmoxStorageCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: storage [{name, pct, used_g, total_g}]
  const storage = Array.isArray(data.storage) ? data.storage : []

  return (
    <div>
      {storage.length > 0 ? (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
            {storage.map((s, i) => (
              <DonutGauge
                key={s.name || i}
                value={s.pct ?? 0}
                max={100}
                color={s.pct > 85 ? 'var(--warn-color, #ffaa00)' : 'var(--gauge-fill-ok, #00ff41)'}
                label={s.name}
                size={52}
              />
            ))}
          </div>
          <SectionHeader>Details</SectionHeader>
          {storage.map((s, i) => (
            <MetricRow
              key={i}
              label={s.name}
              value={s.used_g != null ? `${(s.used_g / 1024).toFixed(1)}T / ${(s.total_g / 1024).toFixed(1)}T (${s.pct}%)` : `${s.pct}%`}
              valueColor={s.pct > 85 ? 'var(--warn-color, #ffaa00)' : undefined}
            />
          ))}
        </>
      ) : (
        <div style={{ fontSize: 11, color: 'var(--text-muted, #555)' }}>No storage data</div>
      )}
    </div>
  )
}
