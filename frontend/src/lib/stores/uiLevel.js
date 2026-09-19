import { derived, get, writable } from 'svelte/store'
import { user } from './user.js'
import { getUiLevels, patchPreferences } from '$lib/api.js'

/**
 * Darstellungsstufen — wie viel der Oberfläche jemand sehen möchte.
 *
 * ⚠️ **Ein Anzeige-Filter, keine Berechtigung.** Was eine Stufe verbirgt, bleibt über
 * Direktlink erreichbar; Rechte stehen allein im Rollenmodell (ADR-003). Wer hier etwas
 * „sperren" will, ist an der falschen Stelle.
 *
 * Die Stufe liegt in `preferences.ui_level` und kommt damit schon mit `$user` mit — nur
 * der Zuschnitt (welcher Eintrag auf welcher Stufe liegt) wird geladen, weil er aus einer
 * Konfigurationsdatei stammt und sich ohne Release ändern darf.
 */
const _registry = writable(null)

/** Der Zuschnitt der eigenen Rolle, oder `null` solange nichts geladen ist. */
export const stufenRegistry = derived(_registry, ($r) => $r)

export async function refreshUiLevels() {
    try {
        _registry.set(await getUiLevels())
    } catch {
        // Ohne Zuschnitt filtert nichts — siehe `sichtbareEintraege`.
    }
}

/**
 * Die wirksame Stufe aus den Einstellungen.
 *
 * Gibt `null` zurück, wenn es für die Rolle keine Stufen gibt — das heißt **kein
 * Filter**, nicht „niedrigste Stufe". Dieselbe Unterscheidung wie im Backend
 * (`stufe_fuer`).
 *
 * Ein gespeicherter Wert außerhalb des Bereichs wird geklemmt: Er darf niemals eine
 * leere Navigation erzeugen, auch wenn er aus einer älteren Konfiguration stammt.
 */
export function wirksameStufe(prefs, registry) {
    if (!registry || !registry.rolle || !registry.stufen?.length) return null
    const roh = Number(prefs?.ui_level)
    if (!Number.isFinite(roh)) return registry.startstufe
    return Math.max(1, Math.min(registry.hoechste, Math.trunc(roh)))
}

/**
 * Die sichtbaren Navigationsschlüssel — kumulativ bis zur eigenen Stufe.
 *
 * `null` heißt **alles zeigen**: kein Zuschnitt geladen, oder eine Rolle ohne Stufen.
 * Der Rückfall geht bewusst in diese Richtung — eine Oberfläche, die wegen eines
 * fehlgeschlagenen Abrufs plötzlich leer ist, wäre der schlimmere Fehler.
 */
export function sichtbareEintraege(registry, stufe) {
    if (!registry || stufe == null) return null
    return new Set(
        registry.stufen.filter((s) => s.stufe <= stufe).flatMap((s) => s.eintraege),
    )
}

/**
 * Die Stufe, zu der ein Navigationseintrag gehört — oder `null`, wenn unbekannt.
 *
 * Für den kontextnahen Einstieg: Wer über einen Direktlink auf einer Seite landet, deren
 * Einstieg seine Stufe verbirgt, soll erfahren **warum** die Oberfläche anders aussieht
 * als beschrieben — nicht abgewiesen werden. Die Seite selbst bleibt erreichbar
 * (Leitprinzip 1: Anzeige-Filter, keine Berechtigung).
 */
export function stufeVon(registry, eintrag) {
    if (!registry) return null
    const treffer = registry.stufen?.find((s) => s.eintraege.includes(eintrag))
    return treffer ? treffer.stufe : null
}

/** Die Stufen oberhalb der eigenen — Grundlage für den Hinweis am Ende der Sidebar. */
export function verborgeneStufen(registry, stufe) {
    if (!registry || stufe == null) return []
    return registry.stufen.filter((s) => s.stufe > stufe)
}

export const uiStufe = derived([user, _registry], ([$u, $r]) =>
    wirksameStufe($u?.preferences, $r),
)

export const sichtbar = derived([_registry, uiStufe], ([$r, $s]) =>
    sichtbareEintraege($r, $s),
)

/** `true`, solange nichts zu filtern ist — dann zeigt die Sidebar alles. */
export const zeigtEintrag = derived(sichtbar, ($s) => (schluessel) =>
    $s === null || $s.has(schluessel),
)

export const naechsteStufen = derived([_registry, uiStufe], ([$r, $s]) =>
    verborgeneStufen($r, $s),
)

/** Stufe setzen — optimistisch, bei Fehler zurückgerollt (Muster von `subjectVisibility`). */
export async function setzeStufe(stufe) {
    const vorher = get(user)
    if (!vorher) return
    user.set({
        ...vorher,
        preferences: { ...(vorher.preferences ?? {}), ui_level: stufe },
    })
    try {
        await patchPreferences({ ui_level: stufe })
    } catch {
        user.set(vorher)
    }
}
