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
import { CONTENT_TYPE_LABELS, PLANUNG_CONTENT_TYPES, RUHENDE_CONTENT_TYPES } from "$lib/taxonomy.js"

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

/**
 * Fertige Auswahlfeld-Einträge: gefiltert, beschriftet, alphabetisch.
 *
 * Drei Auswahlfelder — Filter der Knotenliste, Anlege-Formular, allgemeiner Editor —
 * zeigten den rohen `content_type` (`schuelerpraesentation`, `leitperspektive_aspekt`).
 * Der Wert eines `<option>` bleibt der Schlüssel, sichtbar ist das deutsche Label.
 *
 * **Sortiert wird nach dem Label, nicht nach dem Schlüssel.** Die Reihenfolge der
 * Taxonomie folgt der Herkunft der Typen (Bildungsplan, dann Eigenes) — eine Ordnung,
 * die für Lesende unsichtbar ist, sobald nicht mehr der Schlüssel dasteht.
 *
 * @param {string[]} typen
 * @param {string|null|undefined} aktuellerTyp
 * @returns {Array<{key: string, label: string}>}
 */
export function auswaehlbareTypOptionen(typen, aktuellerTyp = null) {
  return auswaehlbareTypen(typen, aktuellerTyp)
    .map((key) => ({ key, label: CONTENT_TYPE_LABELS[key] ?? key }))
    .sort((a, b) => a.label.localeCompare(b.label, "de"))
}


// ── Unterrichtsplanung in der Bibliothek (0.40, Päckchen AM) ─────────────────
//
// Jahresplan, Unterrichtseinheit und -stunde gehören zur Planung, nicht in die Bibliothek:
// nicht in „Alle Bausteine“, Suche, Facette, Graph und „Neuer Baustein“. „Meine Bausteine“,
// die Detailseite und das Archiv zeigen sie weiter, der Chat findet sie weiter.

const PLANUNG = new Set(PLANUNG_CONTENT_TYPES)

/** Ist das ein Typ der Unterrichtsplanung? */
export function istPlanung(typ) {
  return PLANUNG.has(typ)
}

/**
 * Typenliste ohne Planung — außer dem aktuellen Typ (wie bei ruhenden Typen: eine
 * bestehende Auswahl darf nicht stillschweigend leer werden).
 *
 * @param {string[]} typen
 * @param {string|null|undefined} aktuellerTyp
 */
export function ohnePlanung(typen, aktuellerTyp = null) {
  return (typen ?? []).filter((t) => !PLANUNG.has(t) || t === aktuellerTyp)
}

/** Such-Facette der Bibliothek: auswählbare Typen ohne Planung. */
export function bibliothekTypLabels(aktuellerTyp = null) {
  return auswaehlbareTypLabels(aktuellerTyp).filter(
    ([key]) => !PLANUNG.has(key) || key === aktuellerTyp,
  )
}

/**
 * Graph der Bibliothek ohne Planungsknoten. Der Startknoten bleibt, auch wenn er selbst eine
 * Stunde ist — wer von einer Stunde aus in den Graphen geht, will deren Umgebung sehen.
 * Was danach vom Startknoten aus nicht mehr erreichbar ist, fällt mit weg: Sonst hingen
 * Knoten, die nur über eine Stunde verbunden waren, als Inseln im Bild.
 *
 * @param {Array<{id: string, content_type?: string}>} knoten
 * @param {Array<{from_node_id: string, to_node_id: string}>} kanten
 * @param {string} startId
 */
export function graphOhnePlanung(knoten, kanten, startId) {
  const bleibt = new Set(
    (knoten ?? []).filter((k) => k.id === startId || !PLANUNG.has(k.content_type)).map((k) => k.id),
  )
  const verbunden = (kanten ?? []).filter((e) => bleibt.has(e.from_node_id) && bleibt.has(e.to_node_id))
  const nachbarn = new Map()
  for (const e of verbunden) {
    if (!nachbarn.has(e.from_node_id)) nachbarn.set(e.from_node_id, [])
    if (!nachbarn.has(e.to_node_id)) nachbarn.set(e.to_node_id, [])
    nachbarn.get(e.from_node_id).push(e.to_node_id)
    nachbarn.get(e.to_node_id).push(e.from_node_id)
  }
  const erreicht = new Set(bleibt.has(startId) ? [startId] : [])
  const offen = [...erreicht]
  while (offen.length) {
    for (const n of nachbarn.get(offen.pop()) ?? []) {
      if (!erreicht.has(n)) { erreicht.add(n); offen.push(n) }
    }
  }
  return {
    knoten: (knoten ?? []).filter((k) => erreicht.has(k.id)),
    kanten: verbunden.filter((e) => erreicht.has(e.from_node_id) && erreicht.has(e.to_node_id)),
  }
}
