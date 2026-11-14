/**
 * Einrichtung beim ersten Login (0.43, Plan `Onboarding-Lehrkraefte-Plan.md`) — reine Regeln.
 *
 * Welche Seiten eine Rolle durchgeht, welche entfällt, wo ein Wiedereinstieg beginnt und wann
 * der Dialog von selbst aufgeht. Der Stand kommt von `GET /einrichtung`; Seiteninhalte und
 * Speichern stehen in `EinrichtungDialog.svelte`.
 *
 * **Eine Seite dazunehmen** (etwa für Schüler:innen, 0.47): Schlüssel in `SEITEN`, Liste in
 * `SEITEN_JE_ROLLE`, Inhalt im Dialog. Die gespeicherte Seitennummer zählt in der **vollen**
 * Liste der Rolle — eine entfallene Seite verschiebt den Wiedereinstieg nicht.
 */

export const SEITEN = {
    willkommen: { titel: 'Willkommen' },
    gut_zu_wissen: { titel: 'Gut zu wissen' },
    stufe: { titel: 'Umfang der Oberfläche' },
    stundenplan: { titel: 'Stundenplan' },
    gruppen: { titel: 'Unterrichtsgruppen' },
    fertig: { titel: 'Fertig' },
}

export const SEITEN_JE_ROLLE = {
    teacher: ['willkommen', 'gut_zu_wissen', 'stufe', 'stundenplan', 'gruppen', 'fertig'],
}

/** Die Rolle, nach der sich die Einrichtung richtet — `null`: keine Einrichtung (reine Admins, F10). */
export function einrichtungsRolle(rollen) {
    return (rollen ?? []).includes('teacher') ? 'teacher' : null
}

/**
 * Die Seiten, die tatsächlich gezeigt werden. Ohne Stundenplanquelle entfällt „Stundenplan“.
 * @param {string|null} rolle
 * @param {{ stundenplan?: { configured?: boolean } } | null} daten Antwort von `GET /einrichtung`
 */
export function sichtbareSeiten(rolle, daten) {
    const alle = SEITEN_JE_ROLLE[rolle] ?? []
    return alle.filter((s) => s !== 'stundenplan' || daten?.stundenplan?.configured)
}

/** Nummer einer Seite (ab 1) in der vollen Liste der Rolle — so wird sie gespeichert. */
export function seitenNummer(rolle, seite) {
    return (SEITEN_JE_ROLLE[rolle] ?? []).indexOf(seite) + 1
}

/**
 * Index in `seiten`, an dem ein Durchgang beginnt: bei „später“ dort, wo er stehen blieb (oder
 * der nächsten noch gezeigten Seite), sonst vorn — auch nach „erledigt“, wer ihn erneut aufruft.
 */
export function startIndex(rolle, seiten, daten) {
    if (daten?.stand !== 'spaeter' || !daten?.seite) return 0
    const i = seiten.findIndex((s) => seitenNummer(rolle, s) >= daten.seite)
    return i < 0 ? 0 : i
}

/** „3 von 6“ */
export function fortschritt(index, seiten) {
    return `${index + 1} von ${seiten.length}`
}

/**
 * Geht der Dialog von selbst auf? Nur wenn fällig — und nicht in der Hilfe (F3): Wer dort
 * liest, soll nicht unterbrochen werden; der Dialog kommt auf der nächsten Seite.
 */
export function sollAufgehen(daten, pfad) {
    return Boolean(daten?.faellig) && !String(pfad ?? '').startsWith('/help')
}
