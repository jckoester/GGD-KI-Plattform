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

/**
 * Nur eigene Fachschaften (`subject_department`), nach Fachname sortierbar über
 * `subject_id`.
 *
 * Sie sind der Träger von `write_scope = 'subject'`: Ein Baustein mit diesem Scope
 * **muss** die Gruppe mitführen (DB-CHECK), sonst schlägt das Anlegen fehl. Wo also ein
 * Fach gewählt wird, ist in Wahrheit die Fachschaft gemeint.
 */
export const myFachschaften = derived(_myGroups, $g =>
  $g
    .filter(g => g.type === 'subject_department' && g.subject_id != null)
    .sort((a, b) => a.name.localeCompare(b.name, 'de'))
)

export async function refreshMyGroups() {
  try {
    const data = await getMyGroups()
    _myGroups.set(data.items)
  } catch {
    // Gruppen sind nicht kritisch — UI degradiert graceful
  }
}
