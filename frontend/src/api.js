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

// ── Integration management ────────────────────────────────────────────────────

export async function fetchIntegrations() {
  const r = await fetch(`${BASE}/api/integrations`)
  if (!r.ok) throw new Error(`integrations: ${r.status}`)
  return r.json()
}

export async function saveIntegration(itype, fields) {
  const r = await fetch(`${BASE}/api/integrations/${itype}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  if (!r.ok) throw new Error(`save integration ${itype}: ${r.status}`)
  return r.json()
}

export async function deleteIntegration(itype) {
  const r = await fetch(`${BASE}/api/integrations/${itype}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(`delete integration ${itype}: ${r.status}`)
  return r.json()
}

export async function testIntegration(itype, fields = {}) {
  const r = await fetch(`${BASE}/api/integrations/${itype}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  if (!r.ok) throw new Error(`test integration ${itype}: ${r.status}`)
  return r.json()
}

export async function fetchIntegrationStatus() {
  const r = await fetch(`${BASE}/api/integrations/status`)
  if (!r.ok) throw new Error(`integration status: ${r.status}`)
  return r.json()
}

export async function fetchFirstLaunch() {
  const r = await fetch(`${BASE}/api/first-launch`)
  if (!r.ok) return { first_launch: false, configured_count: 0 }
  return r.json()
}

