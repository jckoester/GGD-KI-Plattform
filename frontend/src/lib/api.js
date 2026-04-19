const BASE = '/api'

export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
    credentials: 'include',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Login fehlgeschlagen')
  }
}

export async function logout() {
  await fetch(`${BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
}

export async function getMe() {
  const res = await fetch(`${BASE}/auth/me`, {
    credentials: 'include',
  })
  if (!res.ok) throw new Error('Nicht angemeldet')
  return res.json()  // { pseudonym, role, grade }
}
