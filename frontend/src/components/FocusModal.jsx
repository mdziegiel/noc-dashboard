import React, { useEffect } from 'react'

export default function FocusModal({ card, data, CardComp, onClose }) {
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  function handleBackdrop(e) {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div
      onClick={handleBackdrop}
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.82)', backdropFilter: 'blur(4px)',
        zIndex: 9000, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div style={{
        background: 'var(--card-background, #111)',
        border: '1px solid var(--card-border, #1e1e1e)',
        borderRadius: 8, padding: 28, maxWidth: 780, width: '92%',
        maxHeight: '85vh', overflowY: 'auto', position: 'relative',
        boxShadow: '0 8px 32px rgba(0,0,0,0.7)',
      }}>
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 10, right: 14, background: 'none',
            border: 'none', color: 'var(--text-muted, #555)', fontSize: 20,
            cursor: 'pointer', lineHeight: 1, padding: '4px 8px',
          }}
          title="Close"
        >&times;</button>
        <div style={{
          fontSize: 15, fontWeight: 700, color: 'var(--accent, #00ff41)',
          letterSpacing: '0.1em', textTransform: 'uppercase',
          marginBottom: 20, paddingRight: 40,
        }}>
          {card.title || card.type}
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-primary, #ccc)' }}>
          {CardComp && data ? (
            <CardComp data={data} config={card.config || {}} />
          ) : (
            <span style={{ color: 'var(--text-muted, #555)' }}>No data available</span>
          )}
        </div>
      </div>
    </div>
  )
}
