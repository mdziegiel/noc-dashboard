import React from 'react'
import { MetricRow, SectionHeader, DonutGauge } from '../shared.jsx'

export default function QnapCard({ data, config, trends }) {
  if (!data) return null
  const units = data.units || (data.volumes ? [data] : [])
  return (
    <div>
      {units.map((unit, ui) => (
        <div key={ui}>
          {units.length > 1 && <SectionHeader>{unit.name || `Unit ${ui + 1}`}</SectionHeader>}
          {(unit.volumes || []).map((v, i) => (
            <MetricRow
              key={i}
              label={v.name || `Volume ${i + 1}`}
              value={v.used != null ? `${v.used} / ${v.total}` : v.status || '—'}
            />
          ))}
          {unit.disk_health && <MetricRow label="Disk Health" value={unit.disk_health} valueColor={unit.disk_health === 'Good' ? 'var(--ok-color, #00ff41)' : 'var(--warn-color, #ffaa00)'} />}
          {unit.temp != null && <MetricRow label="Temp" value={`${unit.temp}°C`} valueColor={unit.temp > 50 ? 'var(--warn-color, #ffaa00)' : undefined} />}
        </div>
      ))}
    </div>
  )
}
