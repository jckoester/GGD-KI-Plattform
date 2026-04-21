import { writable } from 'svelte/store'
import { getRecentConversations } from '$lib/api.js'

export const recentConversations = writable([])

export async function refreshConversations(limit = 10) {
  try {
    const data = await getRecentConversations(limit, 0)
    recentConversations.set(data.items)
  } catch (error) {
    console.error('Fehler beim Laden der Konversationen:', error)
    // Nicht weiterwerfen — UI soll nicht blockieren
  }
}

export function updateConversationTitle(id, title) {
  recentConversations.update(list =>
    list.map(c => c.id === id ? { ...c, title } : c)
  )
}
