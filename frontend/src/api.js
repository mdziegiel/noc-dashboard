const BASE = ''

export async function fetchCardTypes() {
  const r = await fetch(`${BASE}/api/card-types`)
  if (!r.ok) throw new Error(`card-types: ${r.status}`)
  return r.json()
}

export async function fetchThemes() {
  const r = await fetch(`${BASE}/api/themes`)
  if (!r.ok) throw new Error(`themes: ${r.status}`)
  return r.json()
}

export async function fetchLayout() {
  const r = await fetch(`${BASE}/api/layout`)
  if (!r.ok) throw new Error(`layout: ${r.status}`)
  return r.json()
}

export async function saveLayout(layout) {
  const r = await fetch(`${BASE}/api/layout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(layout),
  })
  if (!r.ok) throw new Error(`save layout: ${r.status}`)
  return r.json()
}

export async function fetchConfig() {
  const r = await fetch(`${BASE}/api/config`)
  if (!r.ok) throw new Error(`config: ${r.status}`)
  return r.json()
}

export async function fetchCardData(cardType) {
  const r = await fetch(`${BASE}/api/data/${cardType}`)
  if (!r.ok) throw new Error(`data/${cardType}: ${r.status}`)
  return r.json()
}
