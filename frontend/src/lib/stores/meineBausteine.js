import { writable } from 'svelte/store'
import { getMeineBausteineZaehlung } from '$lib/api.js'

/**
 * Zähler am Sidebar-Eintrag „Meine Bausteine".
 *
 * Er zeigt dieselbe Zahl wie der Warnbanner auf der Seite — beide stammen aus
 * `GET /context/nodes/mine/zaehlung`, nicht aus zwei Rechenwegen. Ohne ihn wäre
 * die Seite rein aufsuchbar; der Zähler ist der Besuchsgrund (Notiz-Knotentyp-UI
 * A4).
 */
export const aufmerksamkeit = writable({
    gesamt: 0,
    laeuft_bald_ab: 0,
    abgelaufen: 0,
    archivierte_referenzen: 0,
    unvollstaendig: 0,
})

export async function refreshAufmerksamkeit() {
    try {
        aufmerksamkeit.set(await getMeineBausteineZaehlung())
    } catch {
        // Bewusst still: Ein Badge ist informativ. Scheitert die Anfrage, steht
        // dort keine Zahl — eine Fehlermeldung in der Sidebar wäre ein
        // Missverhältnis zum Nutzen.
    }
}
