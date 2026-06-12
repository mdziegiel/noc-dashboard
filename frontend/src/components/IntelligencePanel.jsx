import React, { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'
import { fetchIntelligence } from '../api.js'

const COLORS = { ok: 'var(--green)', warn: 'var(--warn)', crit: 'var(--crit)' }
const REFRESH_MS = 30_000

function isGenuineBackdropClick(e, panelSelector) {
  if (!e || e.target !== e.currentTarget) return false
  const doc = document.documentElement
  if (typeof e.clientX === 'number' && (e.clientX >= doc.clientWidth || e.clientY >= doc.clientHeight)) return false
  const panel = panelSelector ? document.querySelector(panelSelector) : null
  const path = typeof e.composedPath === 'function' ? e.composedPath() : []
  if (panel && (panel.contains(e.target) || path.includes(panel))) return false
  return true
}

function healthState(pct) {
  if (pct >= 95) return 'ok'
  if (pct >= 90) return 'warn'
  return 'crit'
}

function Donut({ pct = 0, size = 138 }) {
  const state = healthState(pct)
  const data = [{ name: 'healthy', value: pct }, { name: 'bad', value: Math.max(0, 100 - pct) }]
  return (
    <div className="intel-donut" style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" innerRadius="68%" outerRadius="88%" startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}>
            <Cell fill={COLORS[state]} />
            <Cell fill="rgba(111,138,111,.16)" />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className={`intel-donut-center h-${state}`}>{Math.round(pct)}%</div>
    </div>
  )
}

function Breakdown({ categories = [] }) {
  return (
    <div className="intel-breakdown">
      {categories.map(c => (
        <div key={c.source} className="intel-break-row">
          <span>{c.label}</span>
          <b className={`q-${healthState(c.pct)}`}>{c.good}/{c.total}</b>
        </div>
      ))}
      {categories.length === 0 && <div className="empty">Waiting for collectors...</div>}
    </div>
  )
}

function TrendChart({ data = [] }) {
  const points = data.map(p => ({ ...p, label: new Date(p.ts * 1000).toLocaleString([], { month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' }) }))
  if (!points.length) return <div className="empty">No health history yet. The database is not a clairvoyant.</div>
  return (
    <div style={{ height: 260 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 10, right: 18, bottom: 10, left: 0 }}>
          <CartesianGrid stroke="rgba(111,138,111,.18)" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill:'var(--muted)', fontSize:10 }} minTickGap={28} />
          <YAxis domain={[0, 100]} tick={{ fill:'var(--muted)', fontSize:10 }} />
          <Tooltip contentStyle={{ background:'var(--panel)', border:'1px solid var(--line)', color:'var(--txt)' }} />
          <Line type="monotone" dataKey="pct" stroke="var(--green)" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function HealthDetailModal({ intelligence, onClose }) {
  const [tab, setTab] = useState('overview')
  const [range, setRange] = useState('24h')
  const h = intelligence?.health || { pct: 0, categories: [] }
  return (
    <div className="intel-modal-backdrop" onClick={e => { if (isGenuineBackdropClick(e, '.intel-modal')) onClose() }}>
      <div className="intel-modal">
        <button className="card-modal-close" onClick={onClose}>×</button>
        <div className="card-modal-title">NOC Health Score</div>
        <div className="intel-tabs">
          {['overview','trend','incidents'].map(t => <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t.toUpperCase()}</button>)}
        </div>
        {tab === 'overview' && <div className="intel-overview"><Donut pct={h.pct || 0} /><Breakdown categories={h.categories || []} /></div>}
        {tab === 'trend' && <>
          <div className="intel-range">{['24h','7d','30d'].map(r => <button key={r} className={range === r ? 'active' : ''} onClick={() => setRange(r)}>{r}</button>)}</div>
          <TrendChart data={intelligence?.history?.[range] || []} />
        </>}
        {tab === 'incidents' && <div className="intel-incidents">
          {(intelligence?.incidents || []).slice(0,20).map((i, idx) => (
            <div key={idx} className={`intel-incident q-${i.new_state === 'ok' ? 'ok' : i.new_state === 'warn' ? 'warn' : 'crit'}`}>
              <span>{new Date(i.ts * 1000).toLocaleString()}</span>
              <b>{i.source}</b>
              <em>{i.old_state || 'unknown'} → {i.new_state}</em>
              <p>{i.detail || i.item}</p>
            </div>
          ))}
          {!(intelligence?.incidents || []).length && <div className="empty">No state changes recorded yet.</div>}
        </div>}
      </div>
    </div>
  )
}

function CollapsibleCard({ title, children, defaultOpen = true, className = '' }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={`intel-card ${className}`.trim()}>
      <button className="intel-card-title" onClick={() => setOpen(o => !o)}><span>{title}</span><b>{open ? '−' : '+'}</b></button>
      {open && <div className="intel-card-body">{children}</div>}
    </div>
  )
}

function Bar({ pct }) {
  const cls = pct > 85 ? 'q-crit' : pct >= 70 ? 'q-warn' : 'q-ok'
  return <div className="intel-bar"><span className={cls} style={{ width: `${Math.max(0, Math.min(100, pct || 0))}%` }} /></div>
}

export function IntelligencePanel({ open, onClose, intelligence, onOpenHealth }) {
  const h = intelligence?.health || { pct: 0, categories: [] }
  const backup = intelligence?.backup || {}
  const security = intelligence?.security || {}
  const storage = intelligence?.storage || {}
  const certs = intelligence?.certificates || {}
  return (
    <>
      {open && <div className="intel-overlay" onClick={e => { if (isGenuineBackdropClick(e, '.intel-panel')) onClose() }} />}
      <aside className={`intel-panel${open ? ' open' : ''}`}>
        <div className="intel-panel-hdr"><span>NOC INTELLIGENCE</span><button onClick={onClose}>×</button></div>
        <div className="intel-panel-scroll">
          <CollapsibleCard title="Health Score" className="intel-health-card"><div className="intel-overview compact" onClick={onOpenHealth} role="button" title="Open NOC Health details"><Donut pct={h.pct || 0} size={118} /><Breakdown categories={h.categories || []} /></div></CollapsibleCard>
          <CollapsibleCard title="Backup Coverage" className="intel-backup-card">
            <div className="intel-dual-score"><span>File <b className={`q-${healthState(backup.file_pct || 0)}`}>{backup.file_pct ?? 0}%</b></span><span>Image <b className={`q-${healthState(backup.image_pct || 0)}`}>{backup.image_pct ?? 0}%</b></span></div>
            {(backup.clients || []).map(c => <div key={c.name} className="intel-list-row"><span>{c.name}</span><em>{c.last_file_backup} · image {c.days_since_image_backup ?? 'never'}d</em><b className={`q-${c.status}`}>●</b></div>)}
          </CollapsibleCard>
          <CollapsibleCard title="Security Posture" className="intel-security-card">
            <div className={`intel-big-score q-${security.state || 'ok'}`}>{security.pct ?? 100}%</div>
            {Object.entries(security.breakdown || {}).map(([k,v]) => <div key={k} className="intel-break-row"><span>{k.replaceAll('_',' ')}</span><b>{v}</b></div>)}
          </CollapsibleCard>
          <CollapsibleCard title="Storage Health" className="intel-storage-card">
            <div className="intel-break-row"><span>Total aggregate</span><b>{storage.aggregate_pct ?? 0}% used</b></div><Bar pct={storage.aggregate_pct || 0} />
            {(storage.volumes || []).map(v => <div key={`${v.source}-${v.name}`} className="intel-storage-row"><div><span>{v.name}</span><b>{v.pct}%</b></div><Bar pct={v.pct || 0} /></div>)}
          </CollapsibleCard>
          <CollapsibleCard title="Certificate Expiry" className="intel-cert-card">
            {(certs.flagged || []).length > 0 && <div className="intel-cert-flag">Portainer invalid: {(certs.flagged || []).map(c => c.name).join(', ')}</div>}
            {(certs.certs || []).map(c => {
              const cls = c.valid === false || c.days < 15 ? 'crit' : c.days <= 30 ? 'warn' : 'ok'
              return <div key={`${c.source}-${c.name}`} className="intel-list-row"><span>{c.name}</span><em>{c.source}</em><b className={`q-${cls}`}>{c.valid === false ? 'INVALID' : `${c.days ?? '?'}d`}</b></div>
            })}
          </CollapsibleCard>
        </div>
      </aside>
    </>
  )
}

export function useIntelligence() {
  const [intelligence, setIntelligence] = useState(null)
  useEffect(() => {
    let mounted = true
    async function load() {
      try {
        const data = await fetchIntelligence()
        if (mounted) setIntelligence(data)
      } catch {}
    }
    load()
    const t = setInterval(load, REFRESH_MS)
    return () => { mounted = false; clearInterval(t) }
  }, [])
  return intelligence
}
