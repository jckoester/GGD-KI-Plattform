/**
 * Hinweise auf Neuerungen auf der Startseite (0.17, Plan „Fachbegriffe der Stunde", Schritt 6).
 *
 * Wer was sieht, entscheidet der Server (`app/neuigkeiten/quelle.py`); hier nur das
 * Wegklicken.
 */
import { neuigkeitGelesen } from '$lib/api.js'

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
