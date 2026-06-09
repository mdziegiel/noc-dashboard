import React, { useCallback, useRef, useState, useEffect } from 'react'
import GridLayout from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import CardWrapper from './CardWrapper.jsx'

const COLS = 4
const ROW_HEIGHT = 52
const MARGIN = [8, 8]

export default function CardGrid({ layout, onLayoutChange, onUpdateCard, onRemoveCard, editMode, sseData }) {
  const cards = layout?.cards || []
  const containerRef = useRef(null)
  const [containerWidth, setContainerWidth] = useState(
    typeof window !== 'undefined' ? window.innerWidth - MARGIN[0] * 2 : 1200
  )

  // Track window resize
  useEffect(() => {
    function handleResize() {
      setContainerWidth(window.innerWidth - MARGIN[0] * 2)
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const gridItems = cards.map(card => ({
    i: card.id,
    x: card.x ?? 0,
    y: card.y ?? 0,
    w: card.w ?? 2,
    h: card.h ?? 3,
  }))

  function handleLayoutChange(newItems) {
    const posMap = {}
    newItems.forEach(item => { posMap[item.i] = item })
    const updatedCards = cards.map(card => {
      const pos = posMap[card.id]
      if (!pos) return card
      return { ...card, x: pos.x, y: pos.y, w: pos.w, h: pos.h }
    })
    onLayoutChange({ ...layout, cards: updatedCards })
  }

  if (cards.length === 0) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        gap: 12,
      }}>
        <span style={{ fontSize: 13, color: 'var(--text-muted, #555)', letterSpacing: '0.08em' }}>
          NO CARDS CONFIGURED
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-muted, #333)', letterSpacing: '0.04em' }}>
          {editMode ? 'Click + in the top bar to add a card' : 'Enter edit mode to add cards'}
        </span>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      style={{ padding: `${MARGIN[1]}px ${MARGIN[0]}px 40px` }}
    >
      <GridLayout
        className="layout"
        layout={gridItems}
        cols={COLS}
        rowHeight={ROW_HEIGHT}
        width={containerWidth}
        margin={MARGIN}
        draggableHandle=".card-drag-handle"
        onLayoutChange={handleLayoutChange}
        isDraggable={editMode}
        isResizable={editMode}
        style={{ minHeight: 400 }}
        useCSSTransforms={true}
        preventCollision={false}
      >
        {cards.map(card => (
          <div key={card.id} style={{ display: 'flex', flexDirection: 'column' }}>
            <CardWrapper
              card={card}
              onUpdate={onUpdateCard}
              onRemove={onRemoveCard}
              editMode={editMode}
              sseData={sseData?.[card.type]}
            />
          </div>
        ))}
      </GridLayout>
    </div>
  )
}
