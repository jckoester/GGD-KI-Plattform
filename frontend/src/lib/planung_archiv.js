/**
 * Menüpunkt „Planung“ und Archiv der Planung (0.42, Päckchen AO, Schritt 2).
 *
 * Das Menü zeigt je **aktuelle** Gruppe einen Link in ihren Planer, darunter „Archiv“
 * (Plan F2). Welche Gruppe aktuell ist, sagt das Backend (`GET /planning/groups`, Feld
 * `aktuell`); das Archiv liefert `GET /planning/archive` (F12). Alles im Archiv ist lesend.
 */

/** Einstellung, unter der die Ansicht (Liste oder Kacheln) gemerkt wird. */
export const ANSICHT_SCHLUESSEL = 'planung_archiv_ansicht'
export const ANSICHTEN = ['liste', 'kacheln']

/** Gemerkte Ansicht — Unbekanntes fällt auf Kacheln. */
export function ansichtAusEinstellungen(einstellungen) {
    const roh = einstellungen?.[ANSICHT_SCHLUESSEL]
    return ANSICHTEN.includes(roh) ? roh : 'kacheln'
}

/**
 * Die Gruppen fürs Menü: nur aktuelle mit Fach (der Planer braucht den Fach-Slug),
 * nach Fach, dann Name.
 *
 * `aktuell !== false` wie in `myGroups.js`: Eine Antwort ohne das Feld zeigt alles.
 */
export function menueGruppen(gruppen) {
    return (gruppen ?? [])
        .filter((g) => g.aktuell !== false && g.fach?.slug)
        .sort((a, b) =>
            (a.fach.name ?? '').localeCompare(b.fach.name ?? '', 'de')
            || (a.name ?? '').localeCompare(b.name ?? '', 'de'))
}

export function plannerPfad(gruppe) {
    return `/subjects/${gruppe.fach.slug}/groups/${gruppe.id}/planner`
}

export function archivPfad(groupId, einheit = null) {
    if (groupId == null) return '/planning/archive'
    const basis = `/planning/archive/${groupId}`
    return einheit ? `${basis}?einheit=${encodeURIComponent(einheit)}` : basis
}

/** Der Stundenentwurf öffnet sich im Lesezustand — er liegt unter dem Planer der Gruppe. */
export function stundenPfad(gruppe, stundeId) {
    const slug = gruppe?.fach?.slug ?? '_'
    return `/subjects/${slug}/groups/${gruppe.id}/planner/lessons/${stundeId}`
}

/** Schlüssel der Pseudo-Einheit „Stunden ohne Einheit“ in der Adresse. */
export const OHNE_EINHEIT = 'ohne'

/**
 * Die Einheiten einer Archiv-Gruppe als Kacheln — die Stunden ohne Einheit hinten als
 * eigene Kachel, wenn es welche gibt.
 */
export function einheitenMitOhne(inhalt) {
    const liste = (inhalt?.einheiten ?? []).map((e) => ({ ...e, schluessel: e.id }))
    const ohne = inhalt?.ohne_einheit ?? []
    if (ohne.length) {
        liste.push({
            id: null, schluessel: OHNE_EINHEIT, titel: 'Stunden ohne Einheit', farbe: null,
            schuljahr: null, archiviert: false, stunden: ohne,
        })
    }
    return liste
}

/** Die gewählte Einheit (Adresse `?einheit=`) oder null. */
export function gewaehlteEinheit(inhalt, schluessel) {
    if (!schluessel) return null
    return einheitenMitOhne(inhalt).find((e) => e.schluessel === schluessel) ?? null
}

/** „12 Stunden“, „1 Einheit“ — für Karten und Zeilen. */
export function anzahl(n, einzahl, mehrzahl) {
    return `${n} ${n === 1 ? einzahl : mehrzahl}`
}

/** Datum kurz, deutsch („14.09.2026“); ohne Datum leer. */
export function datumKurz(iso) {
    if (!iso) return ''
    const [j, m, t] = String(iso).slice(0, 10).split('-')
    return `${t}.${m}.${j}`
}
