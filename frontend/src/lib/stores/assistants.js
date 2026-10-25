import { writable, derived } from 'svelte/store'
import { getAssistants } from '$lib/api.js'
import { zurAnzeige } from '$lib/assistentenliste.js'

const _assistants = writable([])

export const assistants = derived(_assistants, $a => $a)

/** Set der subject_ids aller **angezeigten** Assistenten (ohne null) — ein Fach erscheint
 *  in der Seitenleiste nicht wegen eines versteckten Assistenten (0.22, C1). */
export const assistantSubjectIds = derived(_assistants, $a =>
  new Set(zurAnzeige($a).map(a => a.subject_id).filter(Boolean))
)

export async function refreshAssistants() {
  try {
    const data = await getAssistants()
    _assistants.set(data.items ?? [])
  } catch {
    // Non-critical
  }
}
