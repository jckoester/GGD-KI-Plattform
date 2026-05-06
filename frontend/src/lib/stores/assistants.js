import { writable, derived } from 'svelte/store'
import { getAssistants } from '$lib/api.js'

const _assistants = writable([])

export const assistants = derived(_assistants, $a => $a)

/** Set der subject_ids aller zugänglichen Assistenten (ohne null). */
export const assistantSubjectIds = derived(_assistants, $a =>
  new Set($a.map(a => a.subject_id).filter(Boolean))
)

export async function refreshAssistants() {
  try {
    const data = await getAssistants()
    _assistants.set(data.items ?? [])
  } catch {
    // Non-critical
  }
}
