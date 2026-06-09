/**
 * shared.jsx — Primitives matching generate_dashboard.py HTML output exactly.
 * Every function/component here produces the same class names as the Python generator.
 */
import React from 'react'

// metric: <div class="metric m-{state}"><div class="m-v">{val}</div><div class="m-l">{label}</div></div>
export function M({ v, l, s = '' }) {
  return (
    <div className={`metric${s ? ` m-${s}` : ''}`}>
      <div className="m-v">{v ?? '—'}</div>
      <div className="m-l">{l}</div>
    </div>
  )
}

// sub: <div class="sub">{text}</div>
export function Sub({ children }) {
  if (!children) return null
  return <div className="sub">{children}</div>
}

// ubrow: <div class="ubrow {cls}"><span class="ub-n">{n}</span><span class="ub-a">{a}</span></div>
export function UbRow({ n, a, s = '' }) {
  return (
    <div className={`ubrow ${s}`}>
      <span className="ub-n">{n}</span>
      <span className="ub-a">{a}</span>
    </div>
  )
}

// ublist container
export function UbList({ children }) {
  return <div className="ublist">{children}</div>
}

// dv: <div class="dv dv-{on|off}"><span class="dv-dot"></span><span class="dv-name">{name}</span><span class="dv-kind">{kind}</span><span class="dv-up">{up}</span></div>
export function Dv({ name, kind, up, online }) {
  return (
    <div className={`dv dv-${online ? 'on' : 'off'}`}>
      <span className="dv-dot" />
      <span className="dv-name">{name}</span>
      <span className="dv-kind">{kind}</span>
      <span className="dv-up">{up}</span>
    </div>
  )
}

export function DvList({ children }) {
  return <div className="dvlist">{children}</div>
}

// Spark SVG — matches generate_dashboard.py sparkline() function output
// When no trend data: <div class="spark-empty">collecting trend data…</div>
// When data: <svg class="spark sp-{state}" viewBox="0 0 140 34" preserveAspectRatio="none">...</svg>
export function Spark({ data, state = 'ok', label, samples }) {
  const lbl = label || (samples != null ? `${samples} samples / 24h` : null)
  return (
    <div className="trend">
      {lbl && <span className="trend-lbl">{lbl}</span>}
      {(!data || data.length < 2)
        ? <div className="spark-empty">collecting trend data&hellip;</div>
        : <SparkSVG data={data} state={state} />
      }
    </div>
  )
}

function SparkSVG({ data, state }) {
  const values = data.map(d => typeof d === 'number' ? d : (d?.v ?? d?.value ?? 0))
  const W = 140, H = 34
  const min = Math.min(...values), max = Math.max(...values)
  const range = max - min || 1
  const xAt = i => (i / (values.length - 1)) * W
  const yAt = v => H - ((v - min) / range) * (H - 4) - 2
  const pts = values.map((v, i) => `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')
  const areaPts = `0,${H} ` + pts + ` ${W},${H}`
  const lastX = xAt(values.length - 1), lastY = yAt(values[values.length - 1])
  return (
    <svg className={`spark sp-${state}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      <polygon className="spark-area" points={areaPts} />
      <polyline className="spark-line" points={pts} />
      <circle className="spark-dot" cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r="2.5" />
    </svg>
  )
}

// Donut gauge — matches generator's donut() function
export function Donut({ label, pct, state = '' }) {
  const safeState = state || (pct > 85 ? 'crit' : pct > 70 ? 'warn' : '')
  const cls = safeState ? `q-${safeState}` : ''
  const r = 40, cx = 46, cy = 46, circ = 2 * Math.PI * r
  const dash = Math.min(pct / 100, 1) * circ
  const strokeColor = safeState === 'crit' ? 'var(--crit)' : safeState === 'warn' ? 'var(--warn)' : 'var(--green)'
  return (
    <div className="gauge">
      <svg width="92" height="92" viewBox="0 0 92 92">
        <circle className="g-track" cx={cx} cy={cy} r={r} fill="none" strokeWidth="8" />
        <circle cx={cx} cy={cy} r={r} fill="none" strokeWidth="8" stroke={strokeColor}
          strokeDasharray={`${dash.toFixed(1)} ${circ.toFixed(1)}`} strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`} />
        <text x={cx} y={cy} textAnchor="middle" dominantBaseline="middle"
          style={{ fontSize:14, fill:strokeColor, fontFamily:'inherit', fontWeight:700 }}>
          {Math.round(pct)}%
        </text>
      </svg>
      <div className="g-lbl">{label}</div>
    </div>
  )
}

// qbar: <div class="qbar"><span class="qbar-f {cls}" style="width:{pct}%"></span></div>
export function QBar({ pct, state }) {
  const cls = state === 'crit' ? 'q-crit' : state === 'warn' ? 'q-warn' : 'q-ok'
  return (
    <div className="qbar">
      <span className={`qbar-f ${cls}`} style={{ width: `${Math.min(pct, 100)}%` }} />
    </div>
  )
}

// qsec-l: section label inside a QNAP card
export function QSecL({ children }) {
  return <div className="qsec-l">{children}</div>
}

// State helper
export function stateClass(v, warn, crit) {
  if (crit != null && v >= crit) return 'crit'
  if (warn != null && v >= warn) return 'warn'
  if (v === 0) return 'ok'
  return ''
}

// Numeric formatting matching Python's f'{n:,}'
export function fmt(n) {
  if (n == null) return '—'
  return Number(n).toLocaleString('en-US')
}

// Bytes to MB/GB string
export function fmtBytes(b) {
  if (b == null) return '—'
  if (b >= 1e9) return `${(b/1e9).toFixed(1)}GB`
  if (b >= 1e6) return `${(b/1e6).toFixed(1)}MB`
  return `${Math.round(b)}B`
}
