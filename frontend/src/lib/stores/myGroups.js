import { writable, derived } from 'svelte/store'
import { getMyGroups } from '$lib/api.js'

const _myGroups = writable([])
const _geladen = writable(false)

/** Alle eigenen Gruppen (ungefiltert). */
export const myGroups = derived(_myGroups, $g => $g)

/**
 * Ob der erste Abruf durch ist — unabhängig davon, ob er etwas fand.
 *
 * **Wofür:** Eine leere Liste heißt zweierlei — „noch nicht geladen" und „keine
 * Gruppen". Wer beides gleich behandelt, zeigt beim Seitenaufbau kurz die Aussage
 * „dir ist nichts zugeordnet", bevor die Daten da sind. Die Schüler-Weiche auf
 * `/subjects/[slug]` würde sogar auf eine Erklärseite laufen, statt weiterzuleiten.
 *
 * Auch nach einem Fehlschlag `true`: Die Oberfläche degradiert dann bewusst zur
 * ehrlichen Aussage „keine Gruppen", statt endlos zu laden.
 */
export const myGroupsGeladen = derived(_geladen, $g => $g)

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

/**
 * Welche Gruppen zu einem Scope gehören.
 *
 * **Der Fehler, den das behebt:** Beide Knotenformulare boten unter „Fachgruppe"
 * ausschließlich **Unterrichtsgruppen** an — auch bei `write_scope = subject`, wo
 * eine **Fachschaft** gemeint ist. `myFachschaften` gab es bereits, benutzt hat es
 * niemand. Das Backend prüft den Gruppentyp nicht, die falsche Wahl wurde also
 * stumm gespeichert: ein Baustein, der laut Scope der Fachschaft gehört, aber an
 * einer Klasse hängt.
 *
 * @param {string} scope  `read_scope` oder `write_scope`
 * @param {{unterricht?: Array, fachschaften?: Array}} gruppen
 * @returns {Array} leer, wenn der Scope gar keine Gruppe braucht
 */
export function gruppenFuerScope(scope, { unterricht = [], fachschaften = [] } = {}) {
    if (scope === 'subject') return fachschaften
    if (scope === 'group') return unterricht
    return []
}

/**
 * Behält die Auswahl nur, wenn sie in der Liste vorkommt — sonst `null`.
 *
 * Nötig beim Wechsel des Scopes: Die zuvor gewählte Unterrichtsgruppe steht nicht
 * mehr zur Wahl, ihre Id aber noch im Formular. Ohne das Zurücksetzen ginge sie
 * mit `write_scope = subject` an den Server, wo nichts sie ablehnt.
 */
export function gueltigeGruppenwahl(id, gruppen) {
    return (gruppen ?? []).some((g) => g.id === id) ? id : null
}

export async function refreshMyGroups() {
  try {
    const data = await getMyGroups()
    _myGroups.set(data.items)
  } catch {
    // Gruppen sind nicht kritisch — UI degradiert graceful
  } finally {
    _geladen.set(true)
  }
}
