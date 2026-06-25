import { derived, get } from 'svelte/store'
import { user } from './user.js'
import { patchPreferences } from '$lib/api.js'

/**
 * Persönlich ausgeblendete Fächer (subject_ids) aus den Nutzer-Preferences.
 * Liegt in `preferences.hidden_subjects` (JSONB-Array). Pro Lehrkraft, damit
 * Fächer ohne Unterrichtsgruppen (oder nur mit persönlichen Chats) aus der
 * Sidebar genommen werden können.
 */
export const hiddenSubjectIds = derived(user, ($u) =>
  new Set(($u?.preferences?.hidden_subjects ?? []).map(Number)),
)

/**
 * Setzt den Ausgeblendet-Status eines Fachs — optimistisch im Store, dann
 * persistiert über PATCH /preferences. Bei Fehler wird zurückgerollt.
 */
export async function setSubjectHidden(subjectId, hidden) {
  const prev = get(user)
  if (!prev) return
  const next = new Set((prev.preferences?.hidden_subjects ?? []).map(Number))
  if (hidden) next.add(Number(subjectId))
  else next.delete(Number(subjectId))
  const arr = [...next]

  user.set({ ...prev, preferences: { ...(prev.preferences ?? {}), hidden_subjects: arr } })
  try {
    await patchPreferences({ hidden_subjects: arr })
  } catch {
    user.set(prev) // Rollback
  }
}
