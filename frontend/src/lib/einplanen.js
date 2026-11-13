/**
 * Eine Stunde ohne Termin einplanen (0.42.3, Schritt 3; Plan F1) — die Logik hinter
 * `EinplanenDialog.svelte`.
 *
 * Angeboten werden Unterrichtstermine **ohne Entwurf, ab heute**: zuerst die, die schon die
 * Einheit der Stunde tragen (so verteilt man eine kopierte Einheit auf ihre Termine), dann
 * leere. Termine einer **anderen** Einheit nicht. Ein Thema am Termin bleibt; ohne Thema wird
 * der Stundentitel zum Thema.
 *
 * Geschrieben wird über `PATCH /planning/slots/{id}` — dort prüft der Server Gruppe, doppelten
 * Entwurf (409), legt den Wiederherstellungspunkt an und ordnet die Stunde ihrer Einheit zu.
 * Ob der Termin frei ist, prüft er nicht; das sichert `expected_updated_at` (409, wenn sich
 * der Termin seit dem Laden geändert hat).
 */
import { stundenDatum } from './chat_stunde.js'

/** Heute als `YYYY-MM-DD` in Ortszeit. */
export function heuteIso(jetzt = new Date()) {
    const z = (n) => String(n).padStart(2, '0')
    return `${jetzt.getFullYear()}-${z(jetzt.getMonth() + 1)}-${z(jetzt.getDate())}`
}

/** Die Termine, die zur Wahl stehen: `{ eigene, freie }`, je nach Datum und Stunde sortiert. */
export function einplanbareTermine(slots, einheitId, heute) {
    const reihe = (a, b) => a.date.localeCompare(b.date) || (a.start_period ?? 0) - (b.start_period ?? 0)
    const kandidaten = (slots ?? []).filter((s) =>
        s.kategorie === 'unterricht' && !s.stunde_node_id && s.date >= heute)
    return {
        eigene: einheitId ? kandidaten.filter((s) => s.ue_node_id === einheitId).sort(reihe) : [],
        freie: kandidaten.filter((s) => !s.ue_node_id).sort(reihe),
    }
}

/** Was an `updateSlot` geht. */
export function einplanAnfrage(slot, stunde, einheitId) {
    const anfrage = { stunde_node_id: stunde.id, expected_updated_at: slot.updated_at }
    // Ohne Einheit am Termin löste `ordne_entwurf_ein` die Stunde von ihrer Einheit.
    if (einheitId && !slot.ue_node_id) anfrage.ue_node_id = einheitId
    if (!(slot.thema ?? '').trim()) anfrage.thema = stunde.titel
    return anfrage
}

/** „Di 15.9., 3. Std. · Thema“ für die Auswahl. */
export function terminText(slot) {
    const teile = [stundenDatum(slot.date)]
    if (slot.start_period) {
        teile[0] += slot.periods > 1
            ? `, ${slot.start_period}./${slot.start_period + 1}. Std.`
            : `, ${slot.start_period}. Std.`
    }
    if ((slot.thema ?? '').trim()) teile.push(slot.thema.trim())
    return teile.join(' · ')
}
