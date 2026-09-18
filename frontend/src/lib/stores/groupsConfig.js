import { writable, derived } from 'svelte/store'
import { getGroupsConfig } from '$lib/api.js'

// Die Vorgaben gelten, bis die Antwort da ist — und bei Netzwerkfehlern dauerhaft.
// Deshalb je Schalter die harmlose Richtung: manuelle Gruppen erlaubt, und der
// Testbetrieb AUS (sonst verschwänden Fächer, nur weil eine Anfrage scheiterte).
const _config = writable({
    allow_manual_teaching_groups: true,
    student_subjects_opt_in: false,
})

/** Schreibgeschützter Config-Store. */
export const groupsConfig = derived(_config, $c => $c)

export async function refreshGroupsConfig() {
    try {
        const data = await getGroupsConfig()
        _config.set(data)
    } catch {
        // Fallback: die Vorgaben oben bleiben stehen — beide in der harmlosen Richtung.
    }
}
