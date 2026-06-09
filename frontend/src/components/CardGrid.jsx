import React, { useCallback, useRef } from 'react'
import GridLayout from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import CardWrapper from './CardWrapper.jsx'

const COLS = 4
const ROW_HEIGHT = 60
const MARGIN = [12, 12]

export default function CardGrid({ layout, onLayoutChange, onUpdateCard, onRemoveCard }) {
  const cards = layout?.cards || []
  const containerRef = useRef(null)

  // Build react-grid-layout items from cards
  const gridItems = cards.map(card => ({
    i: card.id,
    x: card.x ?? 0,
    y: card.y ?? 0,
    w: card.w ?? 2,
    h: card.h ?? 3,
  }))

  function handleLayoutChange(newItems) {
    // Map updated positions back to cards
    const posMap = {}
    newItems.forEach(item => { posMap[item.i] = item })
    const updatedCards = cards.map(card => {
      const pos = posMap[card.id]
      if (!pos) return card
      return { ...card, x: pos.x, y: pos.y, w: pos.w, h: pos.h }
    })
    onLayoutChange({ ...layout, cards: updatedCards })
  }

  // Compute container width (use window width - paddings)
  const colWidth = typeof window !== 'undefined'
    ? (window.innerWidth - MARGIN[0] * (COLS + 1)) / COLS
    : 200

  return (
    <div ref={containerRef} style={{ padding: `${MARGIN[1]}px ${MARGIN[0]}px 80px` }}>
      <GridLayout
        className="layout"
        layout={gridItems}
        cols={COLS}
        rowHeight={ROW_HEIGHT}
        width={typeof window !== 'undefined' ? window.innerWidth - MARGIN[0] * 2 : 1200}
        margin={MARGIN}
        draggableHandle=".card-drag-handle"
        onLayoutChange={handleLayoutChange}
        isDraggable
        isResizable
        style={{ minHeight: 400 }}
      >
        {cards.map(card => (
          <div key={card.id} style={{ display: 'flex', flexDirection: 'column' }}>
            {/* Invisible drag handle — the entire card header is the drag handle */}
            <CardWrapper
              card={card}
              onUpdate={onUpdateCard}
              onRemove={onRemoveCard}
            />
          </div>
        ))}
      </GridLayout>
    </div>
  )
}
