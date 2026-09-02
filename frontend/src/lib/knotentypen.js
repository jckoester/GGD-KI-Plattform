/**
 * Welche Bausteinarten in einer Auswahl erscheinen (ADR-019 F6, `ui_status`).
 *
 * **Warum ein eigenes Modul.** Fünf Stellen zeigen Typenlisten — das Anlege-Formular,
 * der Editor, der Filter der Knotenliste, die Facette der Suchseite und die
 * Material-Auswahl. Sie müssen dieselbe Regel anwenden, und die Regel hat eine
 * Ausnahme, die man leicht übersieht (siehe unten). Als geteilte Funktion ist sie
 * einmal geschrieben und einmal geprüft.
 *
 * **Ruhend heißt nicht gesperrt.** Ein ruhender Typ verschwindet aus Auswahlflächen,
 * weil es keinen Weg gibt, so einen Knoten anzulegen — ein Angebot, das die Anwendung
 * nicht einlösen kann. Vorhandene Knoten bleiben les-, such- und traversierbar, und die
 * Schnittstelle nimmt sie weiter an.
 */
import { CONTENT_TYPE_LABELS, RUHENDE_CONTENT_TYPES } from "$lib/taxonomy.js"

/**
 * Filtert ruhende Typen aus einer Liste.
 *
 * ⚠️ **Der aktuelle Typ bleibt drin, auch wenn er ruht.** Sonst stünde im Editor eines
 * bestehenden Knotens ein leeres Auswahlfeld, und das Speichern schriebe stillschweigend
 * einen anderen Typ — oder gar keinen. Wer einen ruhenden Knoten bearbeitet, soll ihn
 * unverändert lassen können; er kann nur keinen neuen dieser Art anlegen.
 *
 * @param {string[]} typen
 * @param {string|null|undefined} aktuellerTyp
 * @returns {string[]}
 */
export function auswaehlbareTypen(typen, aktuellerTyp = null) {
  return (typen ?? []).filter(
    (t) => !RUHENDE_CONTENT_TYPES.has(t) || t === aktuellerTyp,
  )
}

/**
 * Dieselbe Regel für Listen aus `[key, label]`-Paaren (Such-Facette).
 *
 * @param {string|null|undefined} aktuellerTyp
 * @returns {Array<[string, string]>}
 */
export function auswaehlbareTypLabels(aktuellerTyp = null) {
  return Object.entries(CONTENT_TYPE_LABELS).filter(
    ([key]) => !RUHENDE_CONTENT_TYPES.has(key) || key === aktuellerTyp,
  )
}
