const BASE = '/api'

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail ?? `Fehler ${status}`)
    this.status = status
  }
}

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
  const data = await res.json()
  // Nur UI-Anzeige; endet mit Tab-Lebenszyklus (sessionStorage)
  sessionStorage.setItem('display_name', data.display_name ?? username)
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
  return res.json()  // { pseudonym, roles: string[], grade }
}

export async function getPreferences() {
  const res = await fetch(`${BASE}/preferences`, { credentials: 'include' })
  if (!res.ok) return {}
  return res.json()
}

export async function patchPreferences(updates) {
  await fetch(`${BASE}/preferences`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(updates),
  })
}

export async function getRecentConversations(limit = 10, offset = 0) {
  const params = new URLSearchParams({ limit, offset })
  const res = await fetch(`${BASE}/conversations?${params}`, { credentials: 'include' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden der Konversationen')
  }
  return res.json()
}

export async function getConversationMessages(conversationId) {
  const res = await fetch(`${BASE}/conversations/${conversationId}/messages`, { credentials: 'include' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    if (res.status === 404) {
      throw new ApiError(404, 'Konversation nicht gefunden')
    }
    if (res.status === 403) {
      throw new ApiError(403, 'Zugriff verweigert')
    }
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden der Konversation')
  }
  return res.json()
}

export async function* streamChat(messages, conversationId = null) {
  let res
  try {
    res = await fetch(`${BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ messages, conversation_id: conversationId }),
    })
  } catch {
    throw new ApiError(0, 'Verbindung zum Server fehlgeschlagen.')
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    // Pydantic-Validierungsfehler liefern detail als Array
    const detail = Array.isArray(body.detail)
      ? body.detail.map(e => e.msg ?? String(e)).join('; ')
      : body.detail
    throw new ApiError(res.status, detail)
  }

  // X-Conversation-Id Header auslesen
  const conversationIdFromHeader = res.headers.get('X-Conversation-Id')
  
  // Erstes Event: start mit conversationId
  if (conversationIdFromHeader) {
    yield { type: 'start', conversationId: conversationIdFromHeader }
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') return
      try {
        const token = JSON.parse(payload).choices?.[0]?.delta?.content
        if (token) yield token
      } catch {
        // unvollständiges JSON oder Metadaten-Zeile — überspringen
      }
    }
  }
}
