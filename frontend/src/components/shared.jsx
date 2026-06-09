import React from 'react'
import { LineChart, Line, Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts'

// Shared metric row: label left, value right
export function MetricRow({ label, value, valueColor, style }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      padding: '2px 0',
      borderBottom: '1px solid var(--card-border, #1e1e1e)',
      fontSize: 11,
      lineHeight: 1.6,
      ...style,
    }}>
      <span style={{ color: 'var(--text-muted, #555)', marginRight: 8 }}>{label}</span>
      <span style={{ color: valueColor || 'var(--text-primary, #e0e0e0)', fontWeight: 500 }}>
        {value ?? '—'}
      </span>
    </div>
  )
}

// Section heading
export function SectionHeader({ children }) {
  return (
    <div style={{
      fontSize: 10,
      textTransform: 'uppercase',
      letterSpacing: '0.1em',
      color: 'var(--section-header-color, #00ff41)',
      marginTop: 8,
      marginBottom: 2,
    }}>
      {children}
    </div>
  )
}

// Small sparkline — 180px wide, 34px tall, no axes
export function Sparkline({ data, color, field = 'value' }) {
  if (!data || data.length < 2) return null
  const points = data.map((d, i) => ({ i, v: typeof d === 'object' ? d[field] ?? d.value ?? 0 : d }))
  const stroke = color || 'var(--graph-line-color, #00ff41)'
  return (
    <div style={{ width: '100%', height: 34, marginTop: 4 }}>
      <ResponsiveContainer width="100%" height={34}>
        <AreaChart data={points} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={stroke} stopOpacity={0.3} />
              <stop offset="95%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="v"
            stroke={stroke}
            strokeWidth={1.5}
            fill="url(#sparkFill)"
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

// SVG donut gauge (0-100%)
export function DonutGauge({ value, max, color, label, size = 56 }) {
  const pct = max ? Math.min(value / max, 1) : Math.min(value / 100, 1)
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const dash = pct * circ
  const c = size / 2
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={c} cy={c} r={r} fill="none" stroke="var(--gauge-track-color, #1a1a1a)" strokeWidth={6} />
        <circle
          cx={c} cy={c} r={r}
          fill="none"
          stroke={color || 'var(--gauge-fill-ok, #00ff41)'}
          strokeWidth={6}
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
          transform={`rotate(-90 ${c} ${c})`}
        />
        <text x={c} y={c + 1} textAnchor="middle" dominantBaseline="middle"
          fontSize="9" fill="var(--text-primary, #e0e0e0)" fontFamily="inherit">
          {Math.round(pct * 100)}%
        </text>
      </svg>
      {label && <span style={{ fontSize: 9, color: 'var(--text-muted, #555)', maxWidth: size, textAlign: 'center', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>}
    </div>
  )
}

// State color helper
export function stateToColor(state) {
  switch (state) {
    case 'ok': return 'var(--ok-color, #00ff41)'
    case 'warn': return 'var(--warn-color, #ffaa00)'
    case 'crit':
    case 'critical': return 'var(--critical-color, #ff0000)'
    case 'error': return 'var(--error-color, #ff3333)'
    case 'degraded': return 'var(--text-muted, #555)'
    default: return 'var(--text-secondary, #a0a0a0)'
  }
}
