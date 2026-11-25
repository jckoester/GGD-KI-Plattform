/**
 * Jahresverlaufspläne der Fachschaften (Päckchen BD, Schritt 5) — reine Funktionen für Ansicht
 * und Editor.
 *
 * Gerechnet wird im Backend (`app/planning/verlaufsplan_zeit.py`): Der Plan speichert nur
 * Reihenfolge und Dauer, der Server legt ihn auf den Kalender des Schuljahrs und liefert die
 * Lage mit (`lage`). Hier liegt nur, was die Oberfläche daraus macht.
 */
import { ueColorIndex } from './planner.js'

/** Richtgröße eines Abschnitts (BD F2): mehr ist erlaubt, wird aber gekennzeichnet. */
export const RICHTGROESSE = 6

/** „15.09.“ aus „2025-09-15“. */
export function tagText(iso) {
    if (!iso) return ''
    const [, m, d] = String(iso).split('-')
    return `${d}.${m}.`
}

/** „15.09.–10.10.“, bei einer Woche ohne Bis nur der Anfang. */
export function zeitraumText(lage) {
    if (!lage?.beginn) return ''
    const von = tagText(lage.beginn)
    const bis = tagText(lage.ende)
    return von === bis ? von : `${von}–${bis}`
}

/** „Woche 5–10“ oder „Woche 5“. */
export function wochenText(lage) {
    if (!lage) return ''
    return lage.von_woche === lage.bis_woche ? `Woche ${lage.von_woche}` : `Woche ${lage.von_woche}–${lage.bis_woche}`
}

/** Was neben einem Abschnitt steht: Ferien, Halbjahr, Länge, Überhang. */
export function hinweise(lage) {
    if (!lage) return []
    const aus = []
    for (const f of lage.ueber_ferien ?? []) aus.push(`über die ${f}`)
    if (lage.vor_ferien) aus.push(`endet vor den ${lage.vor_ferien}`)
    if (lage.halbjahreswechsel) aus.push('Halbjahreswechsel')
    if (lage.lang) aus.push(`länger als ${RICHTGROESSE} Wochen`)
    if (lage.ausserhalb) aus.push(`${lage.ausserhalb} ${lage.ausserhalb === 1 ? 'Woche' : 'Wochen'} nach Schuljahresende`)
    return aus
}

/**
 * Wie viele Wochen ein Abschnitt dauern muss, der in Woche `vonWoche` beginnt und an den
 * nächsten Ferien enden soll (Knopf „bis zu den Ferien“, BD F3). `null` ohne Kalender.
 */
export function wochenBisZuDenFerien(vonWoche, ferienabschnitte) {
    for (const f of ferienabschnitte ?? []) {
        if (f.von_woche <= vonWoche && vonWoche <= f.bis_woche) return f.bis_woche - vonWoche + 1
    }
    return null
}

/** Farbe eines Abschnitts: die seines ersten Kapitels in der Reihenfolge des Curriculums. */
export function abschnittFarbe(abschnitt, kapitelReihenfolge, dark = false) {
    const erstes = abschnitt?.kapitel_ids?.[0]
    const i = erstes ? kapitelReihenfolge.indexOf(String(erstes)) : -1
    return i < 0 ? null : ueColorIndex(i, dark)
}

/** Eine neue, leere Zeile mit der Blocklänge des Plans. */
export function neuerAbschnitt(raster) {
    return { id: null, titel: '', wochen: raster || 1, kapitel_ids: [], notiz: '' }
}

/** Abschnitt `i` um `schritt` Plätze verschieben (−1 hoch, +1 runter); am Rand unverändert. */
export function verschieben(liste, i, schritt) {
    const j = i + schritt
    if (i < 0 || i >= liste.length || j < 0 || j >= liste.length) return liste
    const neu = [...liste]
    const [a] = neu.splice(i, 1)
    neu.splice(j, 0, a)
    return neu
}

/** Abschnitt von Platz `von` an Platz `nach` (Ziehen). */
export function umsetzen(liste, von, nach) {
    if (von === nach || von < 0 || nach < 0 || von >= liste.length || nach >= liste.length) return liste
    const neu = [...liste]
    const [a] = neu.splice(von, 1)
    neu.splice(nach, 0, a)
    return neu
}

/** Laufendes und nächstes Schuljahr — mehr wird nicht neu angelegt. */
export function schuljahreZumAnlegen(aktuell) {
    if (!/^\d{4}\/\d{2}$/.test(aktuell ?? '')) return []
    const start = Number(aktuell.slice(0, 4)) + 1
    return [aktuell, `${start}/${String((start + 1) % 100).padStart(2, '0')}`]
}

/** Wohin sich ein Plan übernehmen lässt: laufendes und nächstes Schuljahr, ohne sein eigenes. */
export function uebernahmeZiele(aktuell, eigenes) {
    return schuljahreZumAnlegen(aktuell).filter((j) => j !== eigenes)
}

/** Pläne, die sich als Ausgangspunkt für einen neuen Plan anbieten: gleiches Fach, gleiche
 *  Stufe, anderes Schuljahr, neueste zuerst (Schritt 6). */
export function ausgangspunkte(plaene, fachId, stufe, schuljahr) {
    if (!stufe) return []
    return (plaene ?? [])
        .filter((p) => p.subject_id === fachId && p.stufe === stufe && p.schuljahr !== schuljahr)
        .sort((a, b) => (a.schuljahr < b.schuljahr ? 1 : -1))
}

/** Pläne eines Fachs: laufende und kommende vorn, das Archiv getrennt (BD F10). */
export function teilen(plaene) {
    const aktuell = []
    const archiv = []
    for (const p of plaene ?? []) (p.archiviert ? archiv : aktuell).push(p)
    const ordnung = (a, b) => (a.schuljahr === b.schuljahr ? (a.stufe ?? 0) - (b.stufe ?? 0)
        : (a.schuljahr < b.schuljahr ? -1 : 1))
    return { aktuell: aktuell.sort(ordnung), archiv: archiv.sort((a, b) => -ordnung(a, b)) }
}

/** Bilanz eines Kapitels: „passt“, „zu wenig“, „zu viel“ oder `null` ohne Zahlen. Ein Spielraum
 *  von einer Wochenstunde gilt als passend. */
export function bilanzStand(kapitel, wochenstunden) {
    if (kapitel?.soll == null || kapitel?.geplant == null) return null
    const spiel = wochenstunden || 0
    if (kapitel.geplant < kapitel.soll - spiel) return 'zu wenig'
    if (kapitel.geplant > kapitel.soll + spiel) return 'zu viel'
    return 'passt'
}

/** Der Plan, wie ihn `PUT` erwartet — ohne berechnete Felder. */
export function zumSpeichern(abschnitte, raster) {
    return {
        raster: raster ?? null,
        abschnitte: (abschnitte ?? []).map((a) => ({
            id: a.id ?? null,
            titel: a.titel ?? '',
            wochen: Number(a.wochen) || 1,
            kapitel_ids: [...(a.kapitel_ids ?? [])],
            notiz: a.notiz ?? '',
        })),
    }
}
