import { writable } from 'svelte/store'
import { getEinrichtung } from '$lib/api.js'

/**
 * Die Einrichtung (0.43): Antwort von `GET /einrichtung` und ob der Dialog offen ist.
 *
 * Ein Store wie beim Feedback-Dialog: Gerendert wird der Dialog einmal im Layout; geöffnet von
 * selbst (fällig) oder später aus „Unterricht“, dem Profil und dem Hinweis auf der Startseite.
 */
export const einrichtung = writable({ daten: null, offen: false })

export async function ladeEinrichtung() {
    try {
        const daten = await getEinrichtung()
        einrichtung.update((e) => ({ ...e, daten }))
        return daten
    } catch {
        // Ohne Antwort kein Dialog — eine fehlende Einrichtung stört weniger als eine kaputte.
        return null
    }
}

export function oeffneEinrichtung() {
    einrichtung.update((e) => ({ ...e, offen: true }))
}

/** Nach dem Schließen: neuer Stand vom Server (oder der alte). */
export function schliesseEinrichtung(daten = null) {
    einrichtung.update((e) => ({ daten: daten ?? e.daten, offen: false }))
}
