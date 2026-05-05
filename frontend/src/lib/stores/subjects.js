import { writable, derived } from 'svelte/store'
import { getSubjects } from '$lib/api.js'

const _subjects = writable([])

/** Geordnete Liste aller Fächer. */
export const subjects = derived(_subjects, $s => $s)

/**
 * Schneller Lookup: subject.id → SubjectOut.
 * Gibt {} zurück, solange Daten noch nicht geladen sind.
 */
export const subjectMap = derived(_subjects, $s =>
  Object.fromEntries($s.map(sub => [sub.id, sub]))
)

/** Lädt Fächer vom Server; Fehler werden stillschweigend ignoriert. */
export async function refreshSubjects() {
  try {
    const data = await getSubjects()
    _subjects.set(data.items)
  } catch {
    // subjects sind optional — UI degradiert graceful (keine Farben)
  }
}
