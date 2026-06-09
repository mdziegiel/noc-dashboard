import React from 'react'
import { M, Sub } from '../shared.jsx'

export default function UrbackupCard({ data, config }) {
  if (!data) return null
  const clients = data.clients || []
  const totalState = data.state === 'warn' ? 'warn' : data.state === 'crit' ? 'crit' : 'ok'
  return (
    <>
      <div className="card-b">
        <M v={`${data.online ?? data.total ?? '?'}/${data.total ?? '?'} online`} l="Clients" s={totalState} />
        {clients.length > 0 && (
          <div className="ublist">
            {clients.map((c, i) => {
              const s = c.state === 'warn' ? 'm-warn' : c.state === 'crit' ? 'm-crit' : ''
              const detail = [c.ago, c.issues > 0 ? `${c.issues} issue(s)` : null].filter(Boolean).join(' · ')
              return (
                <div key={i} className={`ubrow ${s}`}>
                  <span className="ub-n">{c.name}</span>
                  <span className="ub-a">{detail}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}
