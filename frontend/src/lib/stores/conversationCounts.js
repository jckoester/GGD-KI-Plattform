import { writable, derived } from 'svelte/store'
import { getConversationCounts } from '$lib/api.js'

const _counts = writable({ by_subject: {}, by_group: {} })

/** Anzahl Konversationen pro subject_id: { "1": 3, "2": 0, … } */
export const conversationCountsBySubject = derived(_counts, $c => $c.by_subject)

/** Anzahl Konversationen pro group_id: { "5": 2, … } */
export const conversationCountsByGroup = derived(_counts, $c => $c.by_group)

export async function refreshConversationCounts() {
  try {
    const data = await getConversationCounts()
    _counts.set(data)
  } catch {
    // Non-critical — Sidebar zeigt dann "–" statt Anzahl
  }
}
