import React from 'react'
import { MetricRow, SectionHeader, DonutGauge } from '../shared.jsx'

export default function QnapCard({ data, config, trends }) {
  if (!data) return null
  // Collector returns: units [{label, ip, model, cpu_temp, sys_temp, uptime_d, volumes [{name, pct, used_t, total_t}]}]
  const units = data.units || (data.volumes ? [data] : [])
  return (
    <div>
      {units.map((unit, ui) => (
        <div key={ui}>
          {units.length > 1 && <SectionHeader>{unit.label || unit.name || `Unit ${ui + 1}`}</SectionHeader>}
          {unit.model && <MetricRow label="Model" value={unit.model} />}
          {unit.cpu_temp != null && (
            <MetricRow
              label="CPU Temp"
              value={`${unit.cpu_temp}°C`}
              valueColor={unit.cpu_temp > 70 ? 'var(--error-color, #ff3333)' : unit.cpu_temp > 55 ? 'var(--warn-color, #ffaa00)' : undefined}
            />
          )}
          {unit.uptime_d != null && <MetricRow label="Uptime" value={`${unit.uptime_d}d`} />}
          {(unit.volumes || []).length > 0 && (
            <>
              <SectionHeader>Volumes</SectionHeader>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {(unit.volumes || []).map((v, i) => (
                  <DonutGauge
                    key={v.name || i}
                    value={v.pct ?? 0}
                    max={100}
                    color={v.pct > 85 ? 'var(--warn-color, #ffaa00)' : 'var(--gauge-fill-ok, #00ff41)'}
                    label={v.name ? v.name.replace('DataVol', 'Vol') : `V${i + 1}`}
                  />
                ))}
              </div>
              {(unit.volumes || []).map((v, i) => (
                <MetricRow
                  key={i}
                  label={v.name || `Volume ${i + 1}`}
                  value={v.used_t != null ? `${v.used_t}T / ${v.total_t}T` : v.status || '—'}
                  valueColor={v.pct > 85 ? 'var(--warn-color, #ffaa00)' : undefined}
                />
              ))}
            </>
          )}
        </div>
      ))}
    </div>
  )
}
