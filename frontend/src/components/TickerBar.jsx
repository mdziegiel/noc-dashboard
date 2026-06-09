import React, { useState, useEffect, useRef } from 'react'

// Fetch ticker data from the backend
async function fetchTicker() {
  try {
    const r = await fetch('/api/ticker')
    if (!r.ok) return null
    return r.json()
  } catch {
    return null
  }
}

function levelClass(level) {
  switch (level) {
    case 'crit': return 't-crit'
    case 'warn': return 't-warn'
    case 'ok':   return 't-ok'
    default:     return 't-info'
  }
}

function badgeLevelClass(worst) {
  switch (worst) {
    case 'crit':  return 'tb-crit'
    case 'warn':  return 'tb-warn'
    default:      return 'tb-ok'
  }
}

function badgeLabel(worst) {
  switch (worst) {
    case 'crit': return 'ALERT'
    case 'warn': return 'WARN'
    default:     return 'OK'
  }
}

const s = {
  bar: {
    display: 'flex',
    alignItems: 'center',
    background: 'linear-gradient(90deg, #050905, #080e08, #050905)',
    borderBottom: '1px solid var(--top-bar-border, #1a1a1a)',
    height: 30,
    overflow: 'hidden',
    position: 'sticky',
    top: 52,
    zIndex: 90,
    flexShrink: 0,
  },
  badge: {
    flexShrink: 0,
    fontSize: 9,
    fontWeight: 'bold',
    letterSpacing: '2px',
    padding: '0 12px',
    height: '100%',
    display: 'flex',
    alignItems: 'center',
    borderRight: '1px solid var(--top-bar-border, #1a1a1a)',
    whiteSpace: 'nowrap',
    minWidth: 58,
    justifyContent: 'center',
  },
  track: {
    flex: 1,
    overflow: 'hidden',
    height: '100%',
    WebkitMaskImage: 'linear-gradient(90deg, transparent, #000 3%, #000 97%, transparent)',
    maskImage: 'linear-gradient(90deg, transparent, #000 3%, #000 97%, transparent)',
  },
  content: {
    display: 'inline-flex',
    alignItems: 'center',
    height: '100%',
    whiteSpace: 'nowrap',
    // animation speed controlled via inline style based on content length
  },
  item: {
    fontSize: 11,
    letterSpacing: '.4px',
    padding: '0 4px',
  },
  sep: {
    color: '#1e3320',
    margin: '0 12px',
    fontSize: 10,
    flexShrink: 0,
  },
}

export default function TickerBar() {
  const [items, setItems] = useState([])
  const [worst, setWorst] = useState('ok')
  const animRef = useRef(null)

  useEffect(() => {
    let mounted = true

    async function load() {
      const d = await fetchTicker()
      if (!mounted) return
      if (d && d.items && d.items.length > 0) {
        setItems(d.items)
        setWorst(d.worst || 'ok')
      } else {
        setItems([{ text: 'NOC Dashboard — MRDTech // ANTON — Initializing...', level: 'ok' }])
      }
    }

    load()
    // Refresh ticker every 2 minutes
    const t = setInterval(load, 120_000)
    return () => { mounted = false; clearInterval(t) }
  }, [])

  if (items.length === 0) return null

  // Duplicate items for seamless loop (CSS translateX -50% trick)
  const allItems = [...items, ...items]
  // Estimate speed: ~80px per item, 100px/s nominal
  const totalWidth = items.length * 120
  const duration = Math.max(20, totalWidth / 80)

  const badgeClass = badgeLevelClass(worst)
  const badgeStyle = {
    ...s.badge,
    color: worst === 'crit'
      ? 'var(--critical-color, #ff0000)'
      : worst === 'warn'
        ? 'var(--warn-color, #ffaa00)'
        : 'var(--accent, #00ff41)',
    background: worst === 'crit'
      ? 'rgba(255,0,0,0.12)'
      : worst === 'warn'
        ? 'rgba(255,170,0,0.09)'
        : 'rgba(0,255,65,0.07)',
    animation: worst === 'crit' ? 'pulse 1.2s infinite' : 'none',
  }

  return (
    <div style={s.bar} aria-label="Status ticker">
      <div style={badgeStyle}>
        {badgeLabel(worst)}
      </div>
      <div style={s.track}>
        <div
          ref={animRef}
          style={{
            ...s.content,
            animation: `ticker-scroll ${duration}s linear infinite`,
          }}
        >
          {allItems.map((item, i) => (
            <React.Fragment key={i}>
              <span
                style={{
                  ...s.item,
                  color: item.level === 'crit'
                    ? 'var(--critical-color, #ff0000)'
                    : item.level === 'warn'
                      ? 'var(--warn-color, #ffaa00)'
                      : item.level === 'ok'
                        ? 'var(--accent-secondary, #00cc33)'
                        : 'var(--text-muted, #555)',
                  fontWeight: item.level === 'crit' ? 700 : 400,
                }}
              >
                {item.text}
              </span>
              <span style={s.sep}>◆</span>
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  )
}
