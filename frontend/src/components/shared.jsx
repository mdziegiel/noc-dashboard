/**
 * shared.jsx — Shared primitives matching generate_dashboard.py's HTML output exactly.
 * These components emit the same CSS classes as the Python generator so styling is identical.
 */
import React from 'react'
import { AreaChart, Area, ResponsiveContainer } from 'recharts'

// ── Metric row: matches <div class="metric m-{state}"><div class="m-v">...</div><div class="m-l">...</div></div>
export function Metric({ label, value, state }) {
  // state: ok | warn | crit | '' (neutral)
  const cls = state ? `metric m-${state}` : 'metric'
  return (
    <div className={cls}>
      <div className="m-v">{value ?? '—'}</div>
      <div className="m-l">{label}</div>
    </div>
  )
}

// ── Sub text: matches <div class="sub">...</div>
export function Sub({ children }) {
  if (!children) return null
  return <div className="sub">{children}</div>
}

// ── Section header: matches <div class="section-label">...</div>
export function SectionHeader({ children }) {
  return <div className="section-label">{children}</div>
}

// ── Sparkline SVG: matches the generator's sparkline() function output
// <svg class="spark sp-{state}" viewBox="0 0 140 34" preserveAspectRatio="none">
//   <polygon class="spark-area" points="..." />
//   <polyline class="spark-line" points="..." />
//   <circle class="spark-dot" ... />
// </svg>
export function Sparkline({ data, state = 'ok', label }) {
  if (!data || data.length < 2) return null

  const values = data.map(d => typeof d === 'number' ? d : (d?.v ?? d?.value ?? 0))
  const W = 140, H = 34
  const min = Math.min(...values), max = Math.max(...values)
  const range = max - min || 1

  function xAt(i) { return (i / (values.length - 1)) * W }
  function yAt(v) { return H - ((v - min) / range) * (H - 4) - 2 }

  const pts = values.map((v, i) => `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')
  const areaPts = `0,${H} ` + pts + ` ${W},${H}`
  const lastX = xAt(values.length - 1)
  const lastY = yAt(values[values.length - 1])

  return (
    <div className="trend">
      {label && <span className="trend-lbl">{label}</span>}
      <svg className={`spark sp-${state}`} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <polygon className="spark-area" points={areaPts} />
        <polyline className="spark-line" points={pts} />
        <circle className="spark-dot" cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r="2.5" />
      </svg>
    </div>
  )
}

// ── Donut gauge: matches the generator's donut() function
// <svg class="gauge" ...><circle class="g-track" .../><circle class="g-val" .../></svg>
export function DonutGauge({ label, pct, state = 'ok' }) {
  const r = 28, cx = 34, cy = 34
  const circ = 2 * Math.PI * r
  const dash = Math.min(pct / 100, 1) * circ
  const color = state === 'crit' ? 'var(--crit)' : state === 'warn' ? 'var(--warn)' : 'var(--green)'
  return (
    <div className="gauge" style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <svg width="68" height="68" viewBox="0 0 68 68">
        <circle className="g-track" cx={cx} cy={cy} r={r} fill="none" strokeWidth="6" />
        <circle
          className="g-val"
          cx={cx} cy={cy} r={r}
          fill="none" strokeWidth="6"
          stroke={color}
          strokeDasharray={`${dash.toFixed(1)} ${circ.toFixed(1)}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${cx} ${cy})`}
        />
        <text x={cx} y={cy+1} textAnchor="middle" dominantBaseline="middle"
          style={{ fontSize: 12, fill: color, fontFamily: 'inherit', fontWeight: 700 }}>
          {Math.round(pct)}%
        </text>
      </svg>
      <span className="g-lbl" style={{ fontSize: 10, color: 'var(--muted)', textAlign: 'center', maxWidth: 68, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
    </div>
  )
}

// ── Horizontal progress bar: matches qbar/qbar-f
export function QBar({ pct, state = 'ok' }) {
  const color = state === 'crit' ? 'var(--crit)' : state === 'warn' ? 'var(--warn)' : 'var(--green)'
  return (
    <div className="qbar">
      <div className="qbar-f" style={{ width: `${Math.min(pct, 100)}%`, background: color }} />
    </div>
  )
}

// ── H-bar (uptime bar cells) — matches hbar structure
export function HBar({ name, cells, legend }) {
  return (
    <div className="hbar-row">
      <div className="hbar-name">{name}</div>
      <div className="hbar-cells">
        {cells.map((c, i) => (
          <div key={i} className={`hbar-cell b-${c}`} title={c} />
        ))}
      </div>
    </div>
  )
}

// ── MetricRow alias — kept for backward compat but emits Metric
export function MetricRow({ label, value, valueColor, style }) {
  // Map valueColor to state
  let state = ''
  if (valueColor) {
    if (valueColor.includes('ff3') || valueColor.includes('crit')) state = 'crit'
    else if (valueColor.includes('warn') || valueColor.includes('ffaa') || valueColor.includes('ffcc')) state = 'warn'
    else if (valueColor.includes('ok') || valueColor.includes('00ff')) state = 'ok'
  }
  return <Metric label={label} value={value} state={state} />
}

// Keep for backward compat
export const SectionHeader_ = SectionHeader

export function stateToColor(state) {
  switch (state) {
    case 'ok': return 'var(--green)'
    case 'warn': return 'var(--warn)'
    case 'crit': case 'critical': case 'error': return 'var(--crit)'
    default: return 'var(--muted)'
  }
}
