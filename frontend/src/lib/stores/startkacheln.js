/**
 * Welche Kacheln die Startseite zeigt — je Nutzer:in (AP4).
 *
 * Gespeichert in `user_preferences.preferences` als Liste der **ausgeblendeten**
 * Schlüssel. Zwei Gründe für diese Richtung:
 *
 * 1. **Neue Kacheln erscheinen von selbst.** Eine Liste der *sichtbaren* müsste bei
 *    jeder neuen Kachel nachgezogen werden — und wer die Seite einmal eingestellt hat,
 *    bekäme spätere Kacheln nie zu sehen.
 * 2. **Die Vorgabe braucht keinen Eintrag.** Wer nichts einstellt, hat nichts in den
 *    Präferenzen stehen.
 *
 * Keine Sortierung (Entscheidung Jan, F3): Drei Kacheln in fester Reihenfolge sind
 * überschaubar; eine Sortieroberfläche für drei Einträge ist Apparat.
 */
import { derived, get } from "svelte/store"

import { patchPreferences } from "$lib/api.js"
import { user } from "$lib/stores/user.js"

const SCHLUESSEL = "startkacheln_aus"

/** Die Kacheln in fester Reihenfolge — die Reihenfolge ist Teil der Gestaltung. */
export const KACHELN = [
    { id: "heute", name: "Heute" },
    { id: "naechster", name: "Nächster Schultag" },
    { id: "gruppen", name: "Meine Unterrichtsgruppen" },
]

const ausgeblendet = derived(user, ($u) => new Set($u?.preferences?.[SCHLUESSEL] ?? []))

/** Ob eine Kachel gezeigt wird. Unbekannte Schlüssel gelten als sichtbar. */
export const zeigtKachel = derived(ausgeblendet, ($aus) => (id) => !$aus.has(id))

/** Die sichtbaren Kacheln in der festen Reihenfolge. */
export const sichtbareKacheln = derived(ausgeblendet, ($aus) =>
    KACHELN.filter((k) => !$aus.has(k.id)),
)

/** Eine Kachel ein- oder ausblenden — optimistisch, bei Fehler zurückgerollt. */
export async function schalteKachel(id, sichtbar) {
    const vorher = get(user)
    if (!vorher) return
    const aus = new Set(vorher.preferences?.[SCHLUESSEL] ?? [])
    if (sichtbar) aus.delete(id)
    else aus.add(id)
    const liste = [...aus]

    user.set({
        ...vorher,
        preferences: { ...(vorher.preferences ?? {}), [SCHLUESSEL]: liste },
    })
    try {
        await patchPreferences({ [SCHLUESSEL]: liste })
    } catch {
        user.set(vorher)
    }
}
