/**
 * Einen Stundenentwurf löschen (0.42.4; Plan F1–F3).
 *
 * Löschen darf nur, wer die Stunde angelegt hat, und nicht, wenn sie nachbereitet ist — der
 * Server prüft dasselbe (`DELETE /planning/lessons/{id}`). Gelöscht wird endgültig; der Verlauf
 * holt einen gelöschten Entwurf nicht zurück. Deshalb fragt die Oberfläche vorher.
 */
import { stundenDatum } from './chat_stunde.js'

/** Ob eine Stunde aus der Einheitenansicht (`ArchivStundeRead`) gelöscht werden kann. */
export function loeschbar(stunde) {
    return !!stunde?.eigen && !stunde?.nachbereitet
}

/** Die Rückfrage — mit dem Termin, wenn die Stunde eingeplant ist (F2). */
export function loeschFrage(titel, datum = null) {
    const termin = datum
        ? ` Sie ist für ${stundenDatum(datum)} eingeplant; der Termin bleibt mit Thema und Einheit, nur ohne Entwurf.`
        : ''
    return `Stunde „${titel}“ endgültig löschen?${termin} Das lässt sich nicht rückgängig machen.`
}
