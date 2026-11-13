/**
 * Stunden und Einheiten als Vorlage kopieren — die Logik hinter `KopierenDialog.svelte`
 * (0.42, Päckchen AO, Schritt 5).
 *
 * Ziel sind nur eigene **aktuelle** Gruppen **desselben Fachs** (Plan F5); das Backend prüft es
 * ebenso. Eine Stunde braucht eine Zieleinheit — eine bestehende oder eine neue (F6).
 */
import { EINHEITEN, menueGruppen, mitBeschriftung, planerAnsichtPfad, stundenPfad } from './planung_archiv.js'

/** Wert der Auswahl „neue Einheit“ im Einheiten-Feld. */
export const NEUE_EINHEIT = '__neu__'

/** Mögliche Zielgruppen: aktuell, mit Fach, und zwar demselben wie die Quelle — beschriftet wie im Menü. */
export function zielGruppen(gruppen, fachId) {
    if (fachId == null) return []
    return mitBeschriftung(menueGruppen(gruppen).filter((g) => g.fach?.id === fachId))
}

/**
 * Was an den Server geht — oder `null`, solange die Auswahl nicht vollständig ist.
 * Bei der Stunde genau eins von `einheit_id` und `neue_einheit`.
 */
export function kopierAnfrage(art, { gruppeId, einheitWahl, neuerTitel }) {
    if (!gruppeId) return null
    if (art === 'einheit') return { gruppe_id: gruppeId }
    if (einheitWahl === NEUE_EINHEIT) {
        const titel = (neuerTitel ?? '').trim()
        return titel ? { gruppe_id: gruppeId, neue_einheit: titel } : null
    }
    return einheitWahl ? { gruppe_id: gruppeId, einheit_id: einheitWahl } : null
}

/** Wohin der Hauptlink nach dem Kopieren führt: die neue Stunde bzw. die neue Einheit. */
export function ergebnisPfad(art, ergebnis, gruppe) {
    if (!ergebnis || !gruppe?.fach?.slug) return null
    return art === 'stunde' ? stundenPfad(gruppe, ergebnis.id) : einheitenPfad(art, ergebnis, gruppe)
}

/**
 * Die Einheit der Kopie in der Einheitenansicht des Planers (0.42.3) — dort steht sie „ohne
 * Termin“ und lässt sich einplanen. Ohne Termin ist sie in der Jahresübersicht nicht zu sehen.
 */
export function einheitenPfad(art, ergebnis, gruppe) {
    if (!ergebnis || !gruppe?.fach?.slug) return null
    return planerAnsichtPfad(gruppe, EINHEITEN, art === 'stunde' ? ergebnis.einheit_id : ergebnis.id)
}

const ARTEN = { kompetenz: 'Kompetenz', begriff: 'Begriff', material: 'Material', kapitel: 'Kapitel' }

/** Eine Meldung des Servers als Zeile: „Material „AB 1“ (Einstieg): Für die Gruppe nicht freigegeben.“ */
export function meldungText(m) {
    const wo = [m.stunde, m.phase].filter(Boolean).join(', ')
    const was = m.was === 'umgestellt' ? 'umgestellt' : 'nicht übernommen'
    return `${ARTEN[m.art] ?? m.art} „${m.titel}“${wo ? ` (${wo})` : ''} ${was}: ${m.grund}`
}

/** Überschrift über den Meldungen: Was weggelassen und was umgestellt wurde, getrennt gezählt. */
export function meldungenZusammenfassung(meldungen) {
    const weg = (meldungen ?? []).filter((m) => m.was !== 'umgestellt').length
    const um = (meldungen ?? []).length - weg
    const teile = []
    if (weg) teile.push(`${weg} ${weg === 1 ? 'Verweis' : 'Verweise'} nicht übernommen`)
    if (um) teile.push(`${um} auf die Fassung der Gruppe umgestellt`)
    return teile.join(', ')
}
