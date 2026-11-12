/**
 * Angabe „stellt her“ am Assistenten (0.40, Päckchen AM).
 *
 * Die Liste der Arten kommt vom Backend (`app/assistants/produkte.py`,
 * `GET /assistants/produktarten`) — hier steht kein zweites Verzeichnis, nur die
 * Handgriffe darauf. Reihenfolge ist immer die der Liste.
 */
import { getProduktarten } from "$lib/api.js";

let geladen = null;

/** Die Arten, einmal je Sitzung geladen. Bei einem Fehler `[]` — Marken und Auswahl entfallen dann. */
export function ladeProduktarten() {
    if (!geladen) {
        geladen = getProduktarten().catch(() => {
            geladen = null; // beim nächsten Aufruf neu versuchen
            return [];
        });
    }
    return geladen;
}

/** `produces` mit (`an`) oder ohne Art `id`, in Listenreihenfolge. */
export function umgeschaltet(produces, id, an, arten) {
    const gesetzt = new Set(produces ?? []);
    if (an) gesetzt.add(id);
    else gesetzt.delete(id);
    return arten.map((a) => a.id).filter((x) => gesetzt.has(x));
}

/**
 * Beim Einschalten einer Fähigkeit die passende Art dazunehmen — ein Vorschlag, der
 * abwählbar bleibt. Ohne passende Art bleibt `produces` unverändert.
 */
export function mitVorschlag(produces, faehigkeit, arten) {
    const art = arten.find((a) => a.faehigkeit === faehigkeit);
    return art ? umgeschaltet(produces, art.id, true, arten) : (produces ?? []);
}
