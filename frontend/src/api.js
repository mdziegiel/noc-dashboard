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



// ── Authentication ────────────────────────────────────────────────────────────

export async function fetchAuthStatus() {
  const r = await fetch(`${BASE}/api/auth/status`, { credentials: 'include' })
  if (!r.ok) throw new Error(`auth status: ${r.status}`)
  return r.json()
}

export async function setupAdmin(username, password, confirmPassword, remember = true) {
  const r = await fetch(`${BASE}/api/auth/setup`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, confirm_password: confirmPassword, remember }),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `setup: ${r.status}`)
  return r.json()
}

export async function login(username, password, remember = true) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, remember }),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `login: ${r.status}`)
  return r.json()
}

export async function logout() {
  const r = await fetch(`${BASE}/api/auth/logout`, { method: 'POST', credentials: 'include' })
  if (!r.ok) throw new Error(`logout: ${r.status}`)
  return r.json()
}

export async function changePassword(currentPassword, newPassword, confirmPassword) {
  const r = await fetch(`${BASE}/api/auth/change-password`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword, confirm_password: confirmPassword }),
  })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `change password: ${r.status}`)
  return r.json()
}


export async function fetchIntelligence() {
  const r = await fetch(`${BASE}/api/intelligence`)
  if (!r.ok) throw new Error(`intelligence: ${r.status}`)
  return r.json()
}
