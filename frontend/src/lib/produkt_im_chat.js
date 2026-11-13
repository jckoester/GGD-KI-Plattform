/**
 * Produkte aus der Werkstatt im Chat (0.41, Päckchen AN, Schritt 10; Plan F1 a).
 *
 * Unter `@` stehen zwei Gruppen: Bausteine der Bibliothek und — darunter, mit eigener
 * Überschrift — „Aus deiner Werkstatt“. Eine Liste für die Tastatur, zwei Arten Einträge.
 * Dazu die Übergabe aus der Werkstatt („Im Chat verwenden“) an den nächsten neuen Chat.
 */

/**
 * Bausteine und Produkte als **eine** Liste für das Dropdown (Pfeiltasten laufen durch beide).
 * `gruppe` steht am ersten Eintrag einer Gruppe — dort zeigt das Dropdown die Überschrift;
 * die der Bausteine nur, wenn es auch Produkte gibt.
 */
export function mentionEintraege(bausteine = [], produkte = []) {
  const liste = []
  ;(bausteine ?? []).forEach((node, i) =>
    liste.push({
      art: "baustein", schluessel: `b:${node.node_id}`, node,
      gruppe: i === 0 && produkte?.length ? "Bibliothek" : null,
    }),
  )
  ;(produkte ?? []).forEach((produkt, i) =>
    liste.push({
      art: "produkt", schluessel: `p:${produkt.artifact_id}`, produkt,
      gruppe: i === 0 ? "Aus deiner Werkstatt" : null,
    }),
  )
  return liste
}

/** Ein Produkt nur einmal in der Liste der Anhänge. */
export function mitProdukt(liste, produkt) {
  return (liste ?? []).some((p) => p.artifact_id === produkt.artifact_id) ? liste : [...(liste ?? []), produkt]
}

const SCHLUESSEL = "produkt-uebergabe"

/** „Im Chat verwenden“: das Produkt für den nächsten neuen Chat hinterlegen. */
export function produktFuerNeuenChat(produkt) {
  if (typeof sessionStorage === "undefined" || !produkt) return
  sessionStorage.setItem(
    SCHLUESSEL,
    JSON.stringify([{ artifact_id: produkt.artifact_id, kind: produkt.kind, title: produkt.title }]),
  )
}

/** Hinterlegtes abholen — und dabei verbrauchen (wie `context_handover.js`). */
export function produkteUebernehmen() {
  if (typeof sessionStorage === "undefined") return []
  const roh = sessionStorage.getItem(SCHLUESSEL)
  sessionStorage.removeItem(SCHLUESSEL)
  try {
    const liste = JSON.parse(roh ?? "[]")
    return Array.isArray(liste) ? liste.filter((p) => p?.artifact_id) : []
  } catch {
    return []
  }
}

/** Produktarten, die sich im Chat verwenden lassen (wie `ANHAENGBAR` im Backend). */
export const ANHAENGBARE_ARTEN = new Set(["document", "mermaid", "circuit", "plot", "smiles"])
