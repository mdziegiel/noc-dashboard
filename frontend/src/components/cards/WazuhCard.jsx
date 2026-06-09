import React from 'react'
import { M, Sub, Spark, fmt } from '../shared.jsx'

export default function WazuhCard({ data, config }) {
  if (!data) return null
  const down = data.down || []
  const highState = (data.high_24h || 0) > 0 ? 'crit' : ''
  const agentsState = down.length > 0 ? 'warn' : 'ok'
  // Malware sub-metrics from wazuh collector
  const mw = data.malware || {}
  const clamav = mw.clamav ?? data.clamav
  const yara = mw.yara ?? data.yara
  const vt = mw.virustotal ?? data.virustotal
  const defender = mw.defender ?? data.defender
  const subParts = [
    down.length > 0 ? `offline: ${down.join(', ')}` : 'all agents reporting',
    data.malware_note ? `malware: ${data.malware_note}` : null
  ].filter(Boolean)
  return (
    <>
      <div className="card-b">
        <M v={`${data.active ?? data.agents_active ?? '?'}/${data.total ?? data.agents_total ?? '?'} online`} l="Agents" s={agentsState} />
        <M v={fmt(data.alerts_24h)} l="Alerts 24h" />
        <M v={data.high_24h ?? 0} l="High/Crit 24h" s={highState} />
        {(clamav != null || yara != null || vt != null || defender != null) && (
          <div className="ublist">
            <div className="ubrow"><span className="ub-n">Malware Sources</span><span className="ub-a">24h detections</span></div>
          </div>
        )}
        {clamav != null && <M v={clamav} l="ClamAV" s={clamav > 0 ? 'warn' : ''} />}
        {yara != null && <M v={yara} l="YARA" s={yara > 0 ? 'warn' : ''} />}
        {vt != null && <M v={fmt(vt)} l="VirusTotal" s={vt > 0 ? 'warn' : ''} />}
        {defender != null && <M v={defender ?? '—'} l="Defender" />}
        {data._trends?.alerts_24h && <Spark data={data._trends.alerts_24h} state="crit" label={`alerts ${data._trends.alerts_24h.length}d trend`} />}
      </div>
      <Sub>{subParts.join(' | ')}</Sub>
    </>
  )
}
