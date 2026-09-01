/**
 * Bausteine von der Suchseite in einen **neuen** Chat mitgeben.
 *
 * Der Chat puffert angeheftete Knoten ohnehin, solange es noch keine Konversation gibt
 * (`pendingContextNodes`) — es fehlte nur der Weg dorthin. Übergeben wird über
 * `sessionStorage` statt über einen Store: Ein Store überlebt zwar `goto()`, aber kein
 * Neuladen, und die Suchseite lädt beim Sprung in den Chat gelegentlich neu.
 *
 * Einmalig lesbar: `uebernehmen()` löscht den Eintrag. Sonst tauchten dieselben
 * Bausteine beim nächsten neuen Chat erneut auf, ohne dass jemand sie angefordert hat.
 */

const SCHLUESSEL = "kontext-uebergabe";

/** Auswahl für den nächsten neuen Chat hinterlegen. */
export function fuerNeuenChat(knoten) {
  if (typeof sessionStorage === "undefined" || !knoten?.length) return;
  sessionStorage.setItem(
    SCHLUESSEL,
    JSON.stringify(
      knoten.map((n) => ({
        node_id: n.node_id,
        title: n.title,
        category: n.category,
        content_type: n.content_type,
      })),
    ),
  );
}

/** Hinterlegte Auswahl abholen — und dabei verbrauchen. */
export function uebernehmen() {
  if (typeof sessionStorage === "undefined") return [];
  const roh = sessionStorage.getItem(SCHLUESSEL);
  sessionStorage.removeItem(SCHLUESSEL);
  if (!roh) return [];
  try {
    const knoten = JSON.parse(roh);
    return Array.isArray(knoten) ? knoten : [];
  } catch {
    return [];
  }
}
