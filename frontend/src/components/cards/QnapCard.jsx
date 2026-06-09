import React from 'react'
import { M, Sub, QBar, QSecL } from '../shared.jsx'

export default function QnapCard({ data, config }) {
  if (!data) return null
  const units = data.units || []
  if (units.length === 0) return <div className="card-b"><M v="—" l="NAS" /></div>

  return (
    <>
      {units.map((unit, ui) => {
        const volState = unit.volumes?.some(v => v.pct >= 90) ? 'crit' : unit.volumes?.some(v => v.pct >= 80) ? 'warn' : ''
        const cpuState = (unit.cpu_temp || 0) > 65 ? 'crit' : (unit.cpu_temp || 0) > 55 ? 'warn' : ''
        const title = unit.host || unit.label || `QNAP${ui + 1}`
        const ip = unit.ip ? ` · ${unit.ip}` : ''
        return (
          <React.Fragment key={ui}>
            {ui > 0 && <div style={{ borderTop: '1px solid var(--line)', margin: '8px 0 4px' }} />}
            <div className="card-b">
              <M v={unit.cpu_temp ?? '—'} l="CPU °C" s={cpuState} />
              <M v={unit.sys_temp ?? '—'} l="Sys °C" />
              <M v={unit.fan_ok ? 'OK' : 'FAIL'} l="Fan" s={unit.fan_ok ? 'ok' : 'crit'} />
            </div>
            {unit.volumes?.length > 0 && (
              <>
                <QSecL>Volumes</QSecL>
                {unit.volumes.map((vol, vi) => {
                  const vs = vol.pct >= 90 ? 'crit' : vol.pct >= 80 ? 'warn' : ''
                  return (
                    <div key={vi} className="qvol">
                      <div className="qvol-top">
                        <span>{vol.name}</span>
                        <span className={`qvol-pct q-${vs || 'ok'}`}>{Math.round(vol.pct)}%</span>
                      </div>
                      <QBar pct={vol.pct} state={vs || 'ok'} />
                      <div className="qvol-cap">{vol.used_t != null ? `${vol.used_t} / ${vol.total_t} TB` : ''}</div>
                    </div>
                  )
                })}
              </>
            )}
            {unit.disks?.length > 0 && (
              <>
                <QSecL>Disk Health</QSecL>
                {unit.disks.map((disk, di) => {
                  const ds = disk.health !== 'OK' ? 'crit' : ''
                  return (
                    <div key={di} className={`qdisk q-${ds || 'ok'}`}>
                      <span className="qd-dot" />
                      <span className="qd-n">{disk.alias || disk.name}</span>
                      <span className="qd-h">{disk.health}</span>
                      <span className="qd-t">{disk.temp != null ? `${disk.temp}°C` : ''}</span>
                    </div>
                  )
                })}
              </>
            )}
          </React.Fragment>
        )
      })}
    </>
  )
}
