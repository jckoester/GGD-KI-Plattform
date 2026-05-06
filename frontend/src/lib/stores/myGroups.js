import { writable, derived } from 'svelte/store'
import { getMyGroups } from '$lib/api.js'

const _myGroups = writable([])

/** Alle eigenen Gruppen (ungefiltert). */
export const myGroups = derived(_myGroups, $g => $g)

/**
 * Nur eigene teaching_groups, nach subject_id und name sortiert.
 * Reihenfolge: subject_id (null zuletzt), dann alphabetisch.
 */
export const myTeachingGroups = derived(_myGroups, $g =>
  $g
    .filter(g => g.type === 'teaching_group')
    .sort((a, b) => {
      if (a.subject_id !== b.subject_id) {
        if (a.subject_id == null) return 1
        if (b.subject_id == null) return -1
        return a.subject_id - b.subject_id
      }
      return a.name.localeCompare(b.name, 'de')
    })
)

export async function refreshMyGroups() {
  try {
    const data = await getMyGroups()
    _myGroups.set(data.items)
  } catch {
    // Gruppen sind nicht kritisch — UI degradiert graceful
  }
}
