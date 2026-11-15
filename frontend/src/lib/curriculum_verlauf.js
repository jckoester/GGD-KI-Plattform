/**
 * „Rückgängig“ im Curriculum-Editor (0.46): Beschriftung aus dem Verlauf des Backends
 * (`GET /context/curricula/{id}/history` → `{ anzahl, letzter: { zeit, grund, von_mir } }`).
 * Namen gibt es nicht — nur „von dir“, „vom Assistenten“ oder „von jemand anderem“.
 */

function uhrzeit(zeit) {
    const d = new Date(zeit)
    const heute = new Date()
    const gleicherTag = d.toDateString() === heute.toDateString()
    const uhr = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
    return gleicherTag ? uhr : `${d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}, ${uhr}`
}

function wer(letzter) {
    if (letzter.grund === 'assistant') return 'vom Assistenten'
    return letzter.von_mir ? 'von dir' : 'von jemand anderem'
}

/** Ob es etwas zurückzunehmen gibt. */
export function kannZuruecknehmen(verlauf) {
    return !!verlauf?.letzter && (verlauf.anzahl ?? 0) > 0
}

/** Tooltip des Knopfs. */
export function rueckgaengigTitel(verlauf, dirty = false) {
    if (dirty) return 'Erst speichern oder abbrechen'
    if (!kannZuruecknehmen(verlauf)) return 'Noch nichts gespeichert, was sich zurücknehmen ließe'
    const l = verlauf.letzter
    return `Letzte Speicherung zurücknehmen (${uhrzeit(l.zeit)}, ${wer(l)}) — stellt den Stand davor wieder her`
}

/** Meldung nach dem Zurücknehmen. */
export function zurueckgenommenMeldung(antwort) {
    const z = antwort?.zurueckgenommen
    if (!z) return 'Zurückgenommen.'
    const rest = antwort.anzahl ? ` Weitere ${antwort.anzahl} Stände lassen sich zurücknehmen.` : ''
    return `Speicherung von ${uhrzeit(z.zeit)} zurückgenommen.${rest}`
}
