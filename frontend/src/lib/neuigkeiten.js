/**
 * Hinweise auf Neuerungen auf der Startseite (0.17, Plan „Fachbegriffe der Stunde", Schritt 6).
 *
 * Wer was sieht, entscheidet der Server (`app/neuigkeiten/quelle.py`); hier nur, wie viele
 * offen stehen (0.25), und das Wegklicken.
 */
import { neuigkeitGelesen } from '$lib/api.js'

/** So viele Hinweise stehen offen; der Rest wartet unter „Weitere Neuerungen". */
export const OFFEN = 2

/**
 * Teilt die Liste (neueste zuerst, wie vom Server) in die offenen und die weiteren.
 *
 * @returns {{ offen: Array, weitere: Array }}
 */
export function aufteilen(liste, offen = OFFEN) {
    const alle = liste ?? []
    return { offen: alle.slice(0, offen), weitere: alle.slice(offen) }
}

/**
 * Einen Hinweis schließen: sofort ausblenden, dann merken. Scheitert das Merken, bleibt er
 * trotzdem weg — er käme beim nächsten Besuch wieder, mehr nicht.
 *
 * @returns {Promise<Array>} die Liste ohne den Hinweis
 */
export async function schliessen(liste, id, merken = neuigkeitGelesen) {
    const rest = (liste ?? []).filter((n) => n.id !== id)
    try {
        await merken(id)
    } catch {
        // bewusst still — siehe oben
    }
    return rest
}

/**
 * Alle Hinweise schließen. Nacheinander, nicht gleichzeitig: Jeder Aufruf liest und schreibt
 * dieselbe Liste in den Einstellungen, gleichzeitige Aufrufe überschrieben einander.
 *
 * @returns {Promise<Array>} die leere Liste
 */
export async function alleSchliessen(liste, merken = neuigkeitGelesen) {
    for (const n of liste ?? []) {
        try {
            await merken(n.id)
        } catch {
            // wie bei `schliessen`: bewusst still
        }
    }
    return []
}


/**
 * Der Hinweis zur Werkstatt-Reihe (0.40/0.41, F9 bzw. F13 b: eine gemeinsame Neuigkeit). Der
 * Übergangshinweis in Werkstatt und Bibliothek hängt an ihm: Er erscheint, solange die Neuigkeit
 * sichtbar ist, und wer ihn schließt, schließt die Neuigkeit mit. `test_neuigkeiten.py` prüft,
 * dass es die `id` gibt.
 */
export const WERKSTATT_NEUIGKEIT = '0.41-werkstatt-reihe'

/** Steht die Neuigkeit `id` in der Liste des Servers (also: sichtbar und nicht geschlossen)? */
export function istOffen(liste, id) {
    return (liste ?? []).some((n) => n.id === id)
}
