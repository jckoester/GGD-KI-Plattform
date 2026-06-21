const BASE = "/api";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail ?? `Fehler ${status}`);
    this.status = status;
  }
}

export async function login(username, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? "Login fehlgeschlagen");
  }
  const data = await res.json();
  // Nur UI-Anzeige; endet mit Tab-Lebenszyklus (sessionStorage)
  sessionStorage.setItem("display_name", data.display_name ?? username);
}

// Step-up-Re-Authentifizierung (Phase 12): beschreibt den Re-Auth-Weg.
export async function getStepUpChallenge(returnTo = "/welcome") {
  const params = new URLSearchParams({ return_to: returnTo });
  const res = await fetch(`${BASE}/auth/step-up?${params}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { mode: "direct" } | { mode: "redirect", redirect_url }
}

// Step-up im direct-Modus (Dev/Test): Passwort-Re-Entry → setzt stepup-Cookie.
export async function stepUpDirect(username, password) {
  const res = await fetch(`${BASE}/auth/step-up`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { ok: true }
}

export async function logout() {
  await fetch(`${BASE}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function getMe() {
  const res = await fetch(`${BASE}/auth/me`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Nicht angemeldet");
  return res.json(); // { pseudonym, roles: string[], grade }
}

export async function getPreferences() {
  const res = await fetch(`${BASE}/preferences`, { credentials: "include" });
  if (!res.ok) return {};
  return res.json();
}

export async function patchPreferences(updates) {
  await fetch(`${BASE}/preferences`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(updates),
  });
}

export async function getRecentConversations(limit = 10, offset = 0) {
  const params = new URLSearchParams({ limit, offset });
  const res = await fetch(`${BASE}/conversations?${params}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      data.detail ?? "Fehler beim Laden der Konversationen",
    );
  }
  return res.json();
}

/**
 * Lädt Konversationen mit optionalen Filtern.
 * @param {{ limit?: number, offset?: number, subjectId?: number|null, groupId?: number|null }} opts
 */
export async function getConversations({
  limit = 25,
  offset = 0,
  subjectId = null,
  groupId = null,
  excludeGroups = false,
} = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (subjectId != null) params.set("subject_id", subjectId);
  if (groupId != null) params.set("group_id", groupId);
  if (excludeGroups) params.set("exclude_groups", "true");
  const res = await fetch(`${BASE}/conversations?${params}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      data.detail ?? "Fehler beim Laden der Konversationen",
    );
  }
  return res.json(); // { items: ConversationItem[], total: int, limit: int, offset: int }
}

export async function getConversationMessages(conversationId) {
  const res = await fetch(`${BASE}/conversations/${conversationId}/messages`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    if (res.status === 404) {
      throw new ApiError(404, "Konversation nicht gefunden");
    }
    if (res.status === 403) {
      throw new ApiError(403, "Zugriff verweigert");
    }
    throw new ApiError(
      res.status,
      data.detail ?? "Fehler beim Laden der Konversation",
    );
  }
  return res.json();
}

export async function getModels() {
  const res = await fetch(`${BASE}/models`, { credentials: "include" });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      data.detail ?? "Fehler beim Laden der Modelle",
    );
  }
  return res.json();
}

export async function getBudget() {
  try {
    const res = await fetch(`${BASE}/budget/me`, { credentials: "include" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function renameConversation(conversationId, title) {
  const res = await fetch(`${BASE}/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail ?? "Fehler beim Umbenennen");
  }
  return res.json();
}

export async function getMyGroups() {
  const res = await fetch(`${BASE}/groups/me`, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { items: GroupOut[] }
}

export async function getAllGroups() {
  // Nur für Admins als Fallback wenn getMyGroups() leer zurückkommt
  const res = await fetch(`${BASE}/groups`, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { items: GroupOut[] }
}

// Ersetzt patchConversationSubject
export async function patchConversationContext(
  conversationId,
  subjectId,
  groupId,
) {
  // Nur die geänderte Seite senden:
  // group_id gesetzt → Backend leitet subject_id ab; wir senden nur group_id
  // nur subject_id → Lehrkraft-Fach-Ebene
  // beides null → Kein Fach (beide explizit senden)
  let body;
  if (groupId !== undefined && groupId !== null) {
    body = { group_id: groupId };
  } else if (subjectId !== undefined && subjectId !== null) {
    body = { subject_id: subjectId };
  } else {
    body = { group_id: null, subject_id: null };
  }
  const res = await fetch(`${BASE}/conversations/${conversationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      data.detail ?? "Fehler beim Setzen des Fachs",
    );
  }
  return res.json(); // ConversationItem mit aktualisierten subject_id + group_id
}

export async function getConversationCounts() {
  const res = await fetch(`${BASE}/conversations/counts`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { by_subject: { "1": 3 }, by_group: { "5": 2 } }
}

export async function deleteConversation(conversationId) {
  const res = await fetch(`${BASE}/conversations/${conversationId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail ?? "Fehler beim Löschen");
  }
}

export async function getAssistants() {
  const res = await fetch(`${BASE}/assistants`, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { items: AssistantSummary[] }
}

export async function* streamChat(
  messages,
  conversationId = null,
  modelId = null,
  assistantId = null,
  isTest = false,
  subjectId = null,
  groupId = null,
) {
  let res;
  try {
    const body = { messages, conversation_id: conversationId };
    if (modelId) body.model_id = modelId;
    if (assistantId) body.assistant_id = assistantId;
    if (isTest) body.is_test = true;
    // Nur für neue Konversationen (conversationId == null) mitgeben
    if (!conversationId) {
      if (subjectId != null) body.subject_id = subjectId;
      if (groupId != null) body.group_id = groupId;
    }
    res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Verbindung zum Server fehlgeschlagen.");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // Pydantic-Validierungsfehler liefern detail als Array
    const detail = Array.isArray(body.detail)
      ? body.detail.map((e) => e.msg ?? String(e)).join("; ")
      : body.detail;
    throw new ApiError(res.status, detail);
  }

  // X-Conversation-Id Header auslesen
  const conversationIdFromHeader = res.headers.get("X-Conversation-Id");
  const modelFromHeader = res.headers.get("X-Model-Id") || null;
  const assistantIdHeader = res.headers.get("X-Assistant-Id");
  const assistantIdFromHeader = assistantIdHeader ? parseInt(assistantIdHeader) : null;

  // Erstes Event: start mit conversationId, model und assistantId
  if (conversationIdFromHeader) {
    yield { type: "start", conversationId: conversationIdFromHeader, model: modelFromHeader, assistantId: assistantIdFromHeader };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  let currentEventType = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEventType = line.slice(7).trim();
        continue;
      }
      if (line === "") {
        currentEventType = null;
        continue;
      }
      if (!line.startsWith("data: ")) continue;

      const payload = line.slice(6);

      if (currentEventType === "title") {
        try {
          const { title } = JSON.parse(payload);
          yield { type: "title", title };
        } catch {}
        currentEventType = null;
        continue;
      }

      if (currentEventType === "cost") {
        try {
          const { cost_usd } = JSON.parse(payload);
          yield { type: "cost", cost_usd };
        } catch {}
        currentEventType = null;
        continue;
      }

      if (currentEventType === "context_suggestions") {
        try {
          const { nodes } = JSON.parse(payload);
          yield { type: "context_suggestions", nodes };
        } catch {}
        currentEventType = null;
        continue;
      }

      if (currentEventType === "crisis") {
        try {
          yield { type: "crisis", crisis: JSON.parse(payload) };
        } catch {}
        currentEventType = null;
        continue;
      }

      if (payload === "[DONE]") return;
      try {
        const token = JSON.parse(payload).choices?.[0]?.delta?.content;
        if (token) yield token;
      } catch {
        // unvollständiges JSON oder Metadaten-Zeile — überspringen
      }
      currentEventType = null;
    }
  }
}

export async function getModelMatrix() {
  const res = await fetch(`${BASE}/admin/models/matrix`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { models, teams, allowlists }
}

export async function saveModelMatrix(allowlists) {
  const res = await fetch(`${BASE}/admin/models/matrix`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ allowlists }),
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
}

export async function getHeatmap(teamId = null, model = null, weekOffset = 0) {
  const url = new URL(`${BASE}/admin/stats/heatmap`, location.href);
  if (teamId) url.searchParams.set("team_id", teamId);
  if (model) url.searchParams.set("model", model);
  if (weekOffset) url.searchParams.set("week_offset", weekOffset);
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
  // { week_start, week_end, cells: [{dow, hour, count}], team_id, model }
}

export async function getSpend(
  teamId = null,
  model = null,
  fromDate = null,
  toDate = null,
  granularity = null,
) {
  const url = new URL(`${BASE}/admin/stats/spend`, location.href);
  if (teamId) url.searchParams.set("team_id", teamId);
  if (model) url.searchParams.set("model", model);
  if (fromDate) url.searchParams.set("from_date", fromDate);
  if (toDate) url.searchParams.set("to_date", toDate);
  if (granularity) url.searchParams.set("granularity", granularity);
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
  // { entries: [{period, usd, eur}], total_usd, total_eur, eur_usd_rate, team_id, model }
}

export async function getStatsTeams() {
  const res = await fetch(`${BASE}/admin/stats/teams`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // TeamOption[]  { id, label }
}

export async function getStatsModels() {
  const res = await fetch(`${BASE}/admin/stats/models`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // string[]
}

export async function getBudgetGrades() {
  const res = await fetch(`${BASE}/admin/budgets/grades`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
  // { grades: [{key, label, grade, max_budget_eur, budget_duration, user_count}], eur_usd_rate }
}

export async function saveBudgetGrades(grades) {
  // grades: [{key, max_budget_eur}]
  const res = await fetch(`${BASE}/admin/budgets/grades`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grades }),
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { ok, updated_users }
}

export async function getSiteText(key) {
  const res = await fetch(`${BASE}/site-texts/${key}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { key, content, updated_at }
}

export async function saveSiteText(key, content) {
  const res = await fetch(`${BASE}/admin/site-texts/${key}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json(); // { key, updated_at }
}

export async function getGuardrailPrompt() {
  const res = await fetch(`${BASE}/admin/guardrail/prompt`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { prompt: str | null, updated_at: str | null, updated_by: str | null }
}

export async function saveGuardrailPrompt(prompt) {
  const res = await fetch(`${BASE}/admin/guardrail/prompt`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { prompt, updated_at, updated_by }
}

export async function getLiteLLMGuardrails() {
  const res = await fetch(`${BASE}/admin/guardrail/litellm`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { guardrails: [{ name, mode }], available: bool }
}

// Admin: Krisen-/Moderations-Flags (pseudonymisiert, ohne Chat-Inhalte)
export async function getFlags({ status = null, severity = null, limit = 25, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (status) params.set("status", status);
  if (severity) params.set("severity", severity);
  const res = await fetch(`${BASE}/admin/flags?${params}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { items: [...], total, limit, offset }
}

// Admin: Einsicht in eine geflaggte Konversation beantragen (4-Augen-Prinzip)
export async function createAccessRequest(flagId, { reason = null, windowHours = 48 }) {
  const res = await fetch(`${BASE}/admin/flags/${flagId}/access-requests`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason, window_hours: windowHours }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { id, flag_id, conversation_id, status, requested_at, access_window_hours }
}

// review-Rolle: offene Einsicht-Anträge (pseudonymisiert, ohne Inhalte)
export async function getAccessRequests(status = "pending") {
  const params = new URLSearchParams({ status });
  const res = await fetch(`${BASE}/access-requests?${params}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json(); // { items: [...] }
}

// Wirft einen Fehler mit `stepUpRequired = true`, wenn das Backend eine frische
// Authentifizierung verlangt (401 + X-Stepup-Required) — das Frontend öffnet dann
// den Step-up-Dialog und wiederholt die Aktion.
async function _accessAction(id, action) {
  const res = await fetch(`${BASE}/access-requests/${id}/${action}`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) {
    if (res.status === 401 && res.headers.get("X-Stepup-Required")) {
      const err = new ApiError(401, "Re-Authentifizierung erforderlich");
      err.stepUpRequired = true;
      throw err;
    }
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail);
  }
  return res.json();
}

export const approveAccessRequest = (id) => _accessAction(id, "approve");
export const denyAccessRequest = (id) => _accessAction(id, "deny");

export async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  let res;
  try {
    res = await fetch(`${BASE}/upload/session`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
  } catch {
    throw new ApiError(0, "Verbindung zum Server fehlgeschlagen.");
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      data.detail ?? `Upload fehlgeschlagen (${res.status})`,
    );
  }
  return res.json(); // TextUploadResult | ImageUploadResult
}

// Einzelner Assistent (für Bearbeiten) - jetzt gemeinsamer Endpunkt
export async function getAdminAssistant(id) {
  const res = await fetch(`${BASE}/assistants/${id}`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // AssistantResponse
}

// Einzelner Assistent für Lehrkräfte (neu)
export async function getMyAssistant(id) {
  const res = await fetch(`${BASE}/assistants/${id}`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // AssistantResponse
}

// ── Dokument-API ──────────────────────────────────────────────────────────────

export async function uploadAssistantDocument(assistantId, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/assistants/${assistantId}/documents`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // DocumentUploadResponse
}

export async function getAssistantDocuments(assistantId) {
  const res = await fetch(`${BASE}/assistants/${assistantId}/documents`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // AssistantDocumentOut[]
}

export async function deleteAssistantDocument(assistantId, docId) {
  const res = await fetch(`${BASE}/assistants/${assistantId}/documents/${docId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
}

// Liste (mit optionalen Filtern) - Admin-only
export async function getAdminAssistants(params = {}) {
  const url = new URL(`${BASE}/admin/assistants`, location.href);
  Object.entries(params).forEach(
    ([k, v]) => v != null && url.searchParams.set(k, v),
  );
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { items: AssistantResponse[], total: int }
}

// Anlegen - jetzt gemeinsamer Endpunkt
export async function createAssistant(data) {
  const res = await fetch(`${BASE}/assistants`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
}

// Bearbeiten (PATCH) - jetzt gemeinsamer Endpunkt
export async function updateAssistant(id, data) {
  const res = await fetch(`${BASE}/assistants/${id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
}

// Löschen - jetzt gemeinsamer Endpunkt
export async function deleteAssistant(id) {
  const res = await fetch(`${BASE}/assistants/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
}

// Aktivieren
export async function activateAssistant(id) {
  const res = await fetch(`${BASE}/admin/assistants/${id}/activate`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
}

export async function deactivateAssistant(id) {
  const res = await fetch(`${BASE}/admin/assistants/${id}/deactivate`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
}

// Export: YAML-Datei herunterladen - jetzt gemeinsamer Endpunkt
export async function exportAssistant(id, filename) {
  const res = await fetch(`${BASE}/assistants/${id}/export`, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Import: YAML-Datei hochladen (optional mit model_override) - jetzt gemeinsamer Endpunkt
export async function importAssistant(file, modelOverride = null) {
  const form = new FormData();
  form.append("file", file);
  if (modelOverride) form.append("model_override", modelOverride);
  const res = await fetch(`${BASE}/assistants/import`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json();
}

// Import für Lehrkräfte (neu) - alias für importAssistant
export async function importMyAssistant(file, modelOverride = null) {
  return importAssistant(file, modelOverride);
}

// Export aller Assistenten (Admin-only, ZIP)
export async function exportAllAssistants(status = "active") {
  const url = new URL(`${BASE}/admin/assistants/export-all`, location.href);
  if (status) url.searchParams.set("status", status);
  const res = await fetch(url, {
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  const blob = await res.blob();
  const urlObj = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = urlObj;
  a.download = "assistants-export.zip";
  a.click();
  URL.revokeObjectURL(urlObj);
}

export async function getSubjects() {
  const res = await fetch(`${BASE}/subjects`, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { items: SubjectOut[] }
}

// --- Phase 5: Teaching Groups API ---

export async function getPotentialTeachingGroups() {
  const res = await fetch(`${BASE}/groups/teaching/potential`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createTeachingGroup(classGroupId, subjectId) {
  const res = await fetch(`${BASE}/groups/teaching`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      class_group_id: classGroupId,
      subject_id: subjectId,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteTeachingGroup(groupId) {
  const res = await fetch(`${BASE}/groups/teaching/${groupId}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function getExclusions() {
  const res = await fetch(`${BASE}/groups/exclusions`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getGroupsConfig() {
  const res = await fetch(`${BASE}/groups/config`, { credentials: "include" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function addExclusion(classGroupId, subjectId) {
  const res = await fetch(`${BASE}/groups/exclusions`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      class_group_id: classGroupId,
      subject_id: subjectId,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function removeExclusion(classGroupId, subjectId) {
  const res = await fetch(
    `${BASE}/groups/exclusions/${classGroupId}/${subjectId}`,
    {
      method: "DELETE",
      credentials: "include",
    },
  );
  if (!res.ok) throw new Error(await res.text());
}

// ── Teacher: Eigene Assistenten ──────────────────────────────────────────────

export async function getMyAssistants(params = {}) {
  const url = new URL(`${BASE}/assistants/mine`, location.href);
  Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v));
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // { items: TeacherAssistantResponse[], total: int }
}

export async function createMyAssistant(data) {
  const res = await fetch(`${BASE}/assistants`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // TeacherAssistantResponse
}

export async function updateMyAssistant(id, data) {
  const res = await fetch(`${BASE}/assistants/${id}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // TeacherAssistantResponse
}

export async function deleteMyAssistant(id) {
  const res = await fetch(`${BASE}/assistants/${id}`, {
    method: "DELETE",
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
}

export async function submitMyAssistant(id) {
  const res = await fetch(`${BASE}/assistants/${id}/submit`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // TeacherAssistantResponse
}

// Admin: Assistent freigeben
export async function approveAssistant(id) {
  const res = await fetch(`${BASE}/admin/assistants/${id}/approve`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // AssistantResponse
}

// Admin: Assistent ablehnen
export async function rejectAssistant(id, reason = null) {
  const res = await fetch(`${BASE}/admin/assistants/${id}/reject`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok)
    throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail);
  return res.json(); // AssistantResponse
}

// ── Kontext-Anker API (KS-Phase-3 Schritt 5) ────────────────────────────────

/**
 * Lädt alle Kontext-Anker für einen Assistenten
 * @param {number|string} assistantId - Die Assistenten-ID
 * @returns {Promise<ContextAnchorRead[]>} Liste der Anker
 */
export async function getContextAnchors(assistantId) {
  const res = await fetch(`${BASE}/context/assistants/${assistantId}/anchors`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail ?? "Fehler beim Laden der Kontext-Anker");
  }
  return res.json(); // ContextAnchorRead[]
}

/**
 * Fügt einen neuen Kontext-Anker hinzu
 * @param {number|string} assistantId - Die Assistenten-ID
 * @param {string} nodeId - Die Knoten-ID
 * @param {string} role - Die Rolle (z.B. "retrieval_scope")
 * @returns {Promise<ContextAnchorRead>} Der neue Anker
 */
export async function addContextAnchor(assistantId, nodeId, role = "retrieval_scope") {
  const res = await fetch(`${BASE}/context/assistants/${assistantId}/anchors`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, role }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail ?? "Fehler beim Hinzufügen des Kontext-Ankers");
  }
  return res.json(); // ContextAnchorRead
}

/**
 * Entfernt einen Kontext-Anker
 * @param {number|string} assistantId - Die Assistenten-ID
 * @param {string} nodeId - Die Knoten-ID
 * @param {string} role - Die Rolle (z.B. "retrieval_scope")
 */
export async function deleteContextAnchor(assistantId, nodeId, role = "retrieval_scope") {
  const res = await fetch(
    `${BASE}/context/assistants/${assistantId}/anchors/${nodeId}/${role}`,
    {
      method: "DELETE",
      credentials: "include",
    },
  );
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail ?? "Fehler beim Entfernen des Kontext-Ankers");
  }
}

/**
 * Durchsucht Kontext-Knoten nach Titel
 * @param {string} query - Suchbegriff
 * @param {string[]} contentTypes - Content-Types zum Filtern
 * @returns {Promise<ContextNodeResult[]>} Suchergebnisse
 */
export async function searchContextNodesLegacy(query, contentTypes = []) {
  if (query.length < 2) return [];
  
  const params = new URLSearchParams({ q: query });
  contentTypes.forEach((type) => params.append("content_type", type));
  
  const res = await fetch(`${BASE}/context/nodes?${params}`, {
    credentials: "include",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, data.detail ?? "Fehler bei der Knotensuche");
  }
  return res.json(); // ContextNodeResult[]
}

// ── Context Nodes CRUD ──────────────────────────────────────────────────────

/**
 * Lädt Kontextknoten mit optionalen Filtern.
 * @param {{ q?, category?, content_type?, status?, subject_slug?, group_id?, grade?, owner? }} params
 */
export async function getContextNodes(params = {}) {
  const p = new URLSearchParams()
  if (params.q)             p.set('q', params.q)
  if (params.category)      p.set('category', params.category)
  if (params.status)        p.set('status', params.status)
  if (params.subject_slug)  p.set('subject_slug', params.subject_slug)
  if (params.subject_id != null) p.set('subject_id', params.subject_id)
  if (params.subject_id_or_global != null) p.set('subject_id_or_global', params.subject_id_or_global)
  if (params.group_id)      p.set('group_id', params.group_id)
  if (params.grade != null) p.set('grade', params.grade)
  if (params.limit != null) p.set('limit', params.limit)
  if (params.owner)         p.set('owner', params.owner)
  if (params.content_type) {
    const types = Array.isArray(params.content_type) ? params.content_type : [params.content_type]
    types.forEach(t => p.append('content_type', t))
  }
  const res = await fetch(`${BASE}/context/nodes?${p}`, { credentials: 'include' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden der Knoten')
  }
  return res.json()
}

export async function searchContextNodes(query) {
  const res = await fetch(`${BASE}/context/search`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler bei der Kontext-Suche')
  }
  return res.json() // ContextSearchResult[]
}

export async function getContextNode(nodeId) {
  const res = await fetch(`${BASE}/context/nodes/${nodeId}`, { credentials: 'include' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Knoten nicht gefunden')
  }
  return res.json()
}

export async function createContextNode(payload) {
  const res = await fetch(`${BASE}/context/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Erstellen')
  }
  return res.json()
}

export async function updateContextNode(nodeId, payload) {
  const res = await fetch(`${BASE}/context/nodes/${nodeId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Speichern')
  }
  return res.json()
}

export async function deleteContextNode(nodeId) {
  const res = await fetch(`${BASE}/context/nodes/${nodeId}`, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Löschen')
  }
}

export async function getArchivedReferences(nodeId) {
  const res = await fetch(`${BASE}/context/nodes/${nodeId}/archived-references`, {
    credentials: 'include',
  })
  if (!res.ok) return []
  return res.json()
}

export async function copyContextNode(nodeId, payload = {}) {
  const res = await fetch(`${BASE}/context/nodes/${nodeId}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Kopieren')
  }
  return res.json()
}

export async function getNeighborhood(nodeId, { depth = 2, relation = [], category = [] } = {}) {
  const p = new URLSearchParams({ depth })
  relation.forEach(r => p.append('relation', r))
  category.forEach(c => p.append('category', c))
  const res = await fetch(`${BASE}/context/nodes/${nodeId}/neighborhood?${p}`, {
    credentials: 'include',
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden des Graphen')
  }
  return res.json()
}

// ── Chat Context Nodes ──────────────────────────────────────────────────────

export async function getChatContextNodes(conversationId) {
  const res = await fetch(`${BASE}/context/conversations/${conversationId}/nodes`, {
    credentials: 'include',
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json(); // ChatContextNodeRead[]
}

export async function addChatContextNode(conversationId, nodeId) {
  const res = await fetch(`${BASE}/context/conversations/${conversationId}/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ node_id: nodeId }),
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json(); // ChatContextNodeRead
}

export async function removeChatContextNode(conversationId, nodeId) {
  const res = await fetch(
    `${BASE}/context/conversations/${conversationId}/nodes/${nodeId}`,
    { method: 'DELETE', credentials: 'include' },
  );
  if (!res.ok) throw new ApiError(res.status, await res.text());
}

// ============================================================================
// KS-Phase-6 Curriculum API
// ============================================================================

export async function getCurriculum(curriculumId) {
  const res = await fetch(`${BASE}/context/curricula/${curriculumId}`, {
    credentials: 'include'
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Curriculum nicht gefunden')
  }
  return res.json()
}

export async function getCurriculaBySubject(subjectId) {
  const res = await fetch(`${BASE}/context/curricula/by-subject/${subjectId}`, {
    credentials: 'include'
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden der Curricula')
  }
  return res.json()
}

export async function getFachplanBySubject(subjectId, band = null, bpVersion = null) {
  const params = new URLSearchParams()
  if (band) {
    params.set('min_grade', band.min_grade)
    params.set('max_grade', band.max_grade)
    params.set('niveau', band.niveau)
  }
  if (bpVersion) params.set('bp_version', bpVersion)
  const qs = params.toString()
  const url = `${BASE}/context/fachplan/by-subject/${subjectId}${qs ? '?' + qs : ''}`
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden des Bildungsplans')
  }
  return res.json()
}

// Edge API-Funktionen
export async function createEdge(payload) {
  const res = await fetch(`${BASE}/context/edges`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Erstellen der Kante')
  }
  return res.json()
}

export async function deleteEdge(edgeId) {
  const res = await fetch(`${BASE}/context/edges/${edgeId}`, {
    method: 'DELETE',
    credentials: 'include'
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Löschen der Kante')
  }
}

export async function getNodeEdges(nodeId, relation = null) {
  const url = new URL(`${BASE}/context/nodes/${nodeId}/edges`, location.href)
  if (relation) {
    url.searchParams.set('relation', relation.join(','))
  }
  const res = await fetch(url.toString(), { credentials: 'include' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Laden der Kanten')
  }
  return res.json()
}

// Curriculum Create
export async function createCurriculum(payload) {
  const res = await fetch(`${BASE}/context/curricula/new`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(payload)
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, data.detail ?? 'Fehler beim Erstellen des Curriculums')
  }
  return res.json()
}

// ============================================================================
// KS-Phase-6 Schritt 5a: Curriculum Import API
// ============================================================================

export async function getFachplaene() {
    const res = await fetch(
        `${BASE}/context/nodes?content_type=fachplan&status=active`,
        { credentials: 'include' }
    )
    if (!res.ok) throw new ApiError(res.status, 'Fehler beim Laden der Bildungspläne')
    return res.json()
}

export async function createCurriculumFromDraft(draft) {
    const res = await fetch(`${BASE}/context/curricula`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
    })
    if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new ApiError(res.status, data.detail ?? 'Curriculum konnte nicht gespeichert werden')
    }
    return res.json()
}

/**
 * Lädt ein Curriculum als YAML oder PDF herunter.
 * @param {string} curriculumId - UUID des Curriculums
 * @param {string} filename - Dateiname für den Download
 * @param {'yaml'|'pdf'} format - Exportformat
 */
export async function exportCurriculum(curriculumId, filename, format = 'yaml') {
    const res = await fetch(`${BASE}/context/curricula/${curriculumId}/export?format=${format}`, {
        credentials: 'include',
    })
    if (!res.ok)
        throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Export fehlgeschlagen')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
}

// ── Unterrichtsplanung ────────────────────────────────────────────────────────

export async function getPlanningOverview(groupId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/overview`, { credentials: 'include' })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Planungsübersicht konnte nicht geladen werden')
    return res.json()
}

export async function getPlanningOverhang(groupId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/overhang`, { credentials: 'include' })
    if (!res.ok) return []
    return res.json()
}

export async function updateSlot(slotId, updates) {
    const res = await fetch(`${BASE}/planning/slots/${slotId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Slot konnte nicht aktualisiert werden')
    return res.json()
}

export async function swapSlots(groupId, slotAId, slotBId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/slots/swap`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot_a_id: slotAId, slot_b_id: slotBId }),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Tausch fehlgeschlagen')
    return res.json()
}

export async function createUnit(groupId, data) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/units`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'UE konnte nicht erstellt werden')
    return res.json()
}

export async function updateUnit(groupId, nodeId, data) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/units/${nodeId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'UE konnte nicht geändert werden')
    return res.json()
}

export async function deleteUnit(groupId, nodeId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/units/${nodeId}`, {
        method: 'DELETE',
        credentials: 'include',
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'UE konnte nicht gelöscht werden')
}

export async function listUnits(groupId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/units`, { credentials: 'include' })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'UEs konnten nicht geladen werden')
    return res.json()
}

export async function getGroupCurriculumChapters(groupId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/curriculum-chapters`, { credentials: 'include' })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Curriculum-Kapitel konnten nicht geladen werden')
    return res.json()
}

export async function createLesson(unitNodeId, data) {
    const res = await fetch(`${BASE}/planning/units/${unitNodeId}/lessons`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Stunde konnte nicht erstellt werden')
    return res.json()
}

export async function setWeekPattern(groupId, halbjahr, patterns) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/pattern`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ halbjahr, patterns }),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Wochenmuster konnte nicht gespeichert werden')
    return res.json()
}

export async function generateSlots(groupId, halbjahr, regenerate = false) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/slots/generate`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ halbjahr, regenerate }),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Slots konnten nicht generiert werden')
    return res.json()
}

export async function getBalance(groupId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/balance`, { credentials: 'include' })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Bilanz konnte nicht geladen werden')
    return res.json()
}

export async function listSnapshots(groupId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/snapshots`, { credentials: 'include' })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Verlauf konnte nicht geladen werden')
    return res.json()
}

export async function restoreSnapshot(snapshotId) {
    const res = await fetch(`${BASE}/planning/snapshots/${snapshotId}/restore`, {
        method: 'POST',
        credentials: 'include',
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Wiederherstellung fehlgeschlagen')
    return res.json()
}

export async function getLesson(nodeId) {
    const res = await fetch(`${BASE}/planning/lessons/${nodeId}`, { credentials: 'include' })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Stunde konnte nicht geladen werden')
    return res.json()
}

export async function patchLesson(nodeId, updates) {
    const res = await fetch(`${BASE}/planning/lessons/${nodeId}`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Stunde konnte nicht gespeichert werden')
    return res.json()
}

export async function exportLesson(nodeId, format = 'md') {
    const res = await fetch(`${BASE}/planning/lessons/${nodeId}/export?format=${format}`, {
        credentials: 'include',
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Export fehlgeschlagen')
    return res.blob()
}

export async function createReview(slotId, payload) {
    const res = await fetch(`${BASE}/planning/slots/${slotId}/review`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Nachbereitung fehlgeschlagen')
    return res.json()
}

export async function deleteReview(slotId) {
    const res = await fetch(`${BASE}/planning/slots/${slotId}/review`, {
        method: 'DELETE',
        credentials: 'include',
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Undo fehlgeschlagen')
    return res.json()
}

export async function getReviewStatus(groupId) {
    const res = await fetch(`${BASE}/planning/groups/${groupId}/review-status`, {
        credentials: 'include',
    })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Review-Status konnte nicht geladen werden')
    return res.json()
}
