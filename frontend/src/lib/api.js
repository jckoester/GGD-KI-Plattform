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

export async function getModels() {
  const res = await fetch(`${BASE}/models`, { credentials: 'include' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden der Modelle')
  }
  return res.json()
}

export async function getBudget() {
  try {
    const res = await fetch(`${BASE}/budget/me`, { credentials: 'include' })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function renameConversation(conversationId, title) {
  const res = await fetch(`${BASE}/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ title }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Umbenennen')
  }
  return res.json()
}

export async function deleteConversation(conversationId) {
  const res = await fetch(`${BASE}/conversations/${conversationId}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Löschen')
  }
}

export async function getAssistants() {
  const res = await fetch(`${BASE}/assistants`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // { items: AssistantSummary[] }
}

export async function* streamChat(messages, conversationId = null, modelId = null, assistantId = null, isTest = false) {
  let res
  try {
    const body = { messages, conversation_id: conversationId }
    if (modelId)     body.model_id     = modelId
    if (assistantId) body.assistant_id = assistantId
    if (isTest)     body.is_test      = true
    res = await fetch(`${BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(body),
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

  let currentEventType = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEventType = line.slice(7).trim()
        continue
      }
      if (line === '') {
        currentEventType = null
        continue
      }
      if (!line.startsWith('data: ')) continue

      const payload = line.slice(6)

      if (currentEventType === 'title') {
        try {
          const { title } = JSON.parse(payload)
          yield { type: 'title', title }
        } catch {}
        currentEventType = null
        continue
      }

      if (currentEventType === 'cost') {
        try {
          const { cost_usd } = JSON.parse(payload)
          yield { type: 'cost', cost_usd }
        } catch {}
        currentEventType = null
        continue
      }

      if (payload === '[DONE]') return
      try {
        const token = JSON.parse(payload).choices?.[0]?.delta?.content
        if (token) yield token
      } catch {
        // unvollständiges JSON oder Metadaten-Zeile — überspringen
      }
      currentEventType = null
    }
  }
}

export async function getModelMatrix() {
  const res = await fetch(`${BASE}/admin/models/matrix`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // { models, teams, allowlists }
}

export async function saveModelMatrix(allowlists) {
  const res = await fetch(`${BASE}/admin/models/matrix`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ allowlists }),
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
}

export async function getHeatmap(teamId = null, model = null, weekOffset = 0) {
  const url = new URL(`${BASE}/admin/stats/heatmap`, location.href)
  if (teamId) url.searchParams.set('team_id', teamId)
  if (model) url.searchParams.set('model', model)
  if (weekOffset) url.searchParams.set('week_offset', weekOffset)
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
  // { week_start, week_end, cells: [{dow, hour, count}], team_id, model }
}

export async function getSpend(
  teamId = null,
  model = null,
  fromDate = null,
  toDate = null,
  granularity = null,
) {
  const url = new URL(`${BASE}/admin/stats/spend`, location.href)
  if (teamId) url.searchParams.set('team_id', teamId)
  if (model) url.searchParams.set('model', model)
  if (fromDate) url.searchParams.set('from_date', fromDate)
  if (toDate) url.searchParams.set('to_date', toDate)
  if (granularity) url.searchParams.set('granularity', granularity)
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
  // { entries: [{period, usd, eur}], total_usd, total_eur, eur_usd_rate, team_id, model }
}

export async function getStatsTeams() {
  const res = await fetch(`${BASE}/admin/stats/teams`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // TeamOption[]  { id, label }
}

export async function getStatsModels() {
  const res = await fetch(`${BASE}/admin/stats/models`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // string[]
}

export async function getBudgetGrades() {
  const res = await fetch(`${BASE}/admin/budgets/grades`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
  // { grades: [{key, label, grade, max_budget_eur, budget_duration, user_count}], eur_usd_rate }
}

export async function saveBudgetGrades(grades) {
  // grades: [{key, max_budget_eur}]
  const res = await fetch(`${BASE}/admin/budgets/grades`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grades }),
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // { ok, updated_users }
}

export async function getSiteText(key) {
  const res = await fetch(`${BASE}/site-texts/${key}`, { credentials: 'include' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()   // { key, content, updated_at }
}

export async function saveSiteText(key, content) {
  const res = await fetch(`${BASE}/admin/site-texts/${key}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()   // { key, updated_at }
}

export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  let res
  try {
    res = await fetch(`${BASE}/upload/session`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    })
  } catch {
    throw new ApiError(0, 'Verbindung zum Server fehlgeschlagen.')
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? `Upload fehlgeschlagen (${res.status})`)
  }
  return res.json()  // TextUploadResult | ImageUploadResult
}

// Einzelner Assistent (für Bearbeiten)
export async function getAdminAssistant(id) {
  const res = await fetch(`${BASE}/admin/assistants/${id}`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // AssistantResponse
}

// Liste (mit optionalen Filtern)
export async function getAdminAssistants(params = {}) {
  const url = new URL(`${BASE}/admin/assistants`, location.href)
  Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v))
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // { items: AssistantResponse[], total: int }
}

// Anlegen
export async function createAssistant(data) {
  const res = await fetch(`${BASE}/admin/assistants`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
}

// Bearbeiten (PATCH)
export async function updateAssistant(id, data) {
  const res = await fetch(`${BASE}/admin/assistants/${id}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
}

// Löschen
export async function deleteAssistant(id) {
  const res = await fetch(`${BASE}/admin/assistants/${id}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
}

// Aktivieren
export async function activateAssistant(id) {
  const res = await fetch(`${BASE}/admin/assistants/${id}/activate`, {
    method: 'POST', credentials: 'include',
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
}

export async function deactivateAssistant(id) {
  const res = await fetch(`${BASE}/admin/assistants/${id}/deactivate`, {
    method: 'POST', credentials: 'include',
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
}

// Export: YAML-Datei herunterladen
export async function exportAssistant(id, filename) {
  const res = await fetch(`${BASE}/admin/assistants/${id}/export`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// Import: YAML-Datei hochladen (optional mit model_override)
export async function importAssistant(file, modelOverride = null) {
  const form = new FormData()
  form.append('file', file)
  if (modelOverride) form.append('model_override', modelOverride)
  const res = await fetch(`${BASE}/admin/assistants/import`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()
}

export async function getSubjects() {
  const res = await fetch(`${BASE}/subjects`, { credentials: 'include' })
  if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail)
  return res.json()  // { items: SubjectOut[] }
}
