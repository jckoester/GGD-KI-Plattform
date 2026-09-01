/**
 * Suchergebnisse für die Dauer der Sitzung behalten.
 *
 * **Wofür.** Wer einen Treffer öffnet und zurückkommt, soll seine Liste wiederfinden,
 * ohne erneut zu warten. Eine Suche kostet rund 400 ms, und davon entfallen etwa 370 ms
 * auf den Netzaufruf zum Embedding-Modell (gemessen 01.09.2026) — das ist keine
 * Wartezeit, die man für ein unverändertes Ergebnis zweimal zumuten muss.
 *
 * **Warum das vertretbar ist.** Der Wissensgraph ändert sich nicht, während jemand einen
 * Baustein ansieht. Der Cache wird deshalb ausschließlich beim **Zurückkehren** gelesen;
 * wer den Suchknopf drückt oder eine Facette ändert, sucht neu. Beim Neuladen ist er weg
 * — er lebt im Modulzustand, nicht im Speicher des Browsers.
 *
 * **Die eine Unschärfe:** Wer einen Knoten in der Detailansicht umbenennt und
 * zurückgeht, sieht kurz den alten Titel. Eine erneute Suche räumt das auf. Den Cache
 * dafür bei jeder Bearbeitung zu verwerfen, hieße die halbe Anwendung von ihm wissen zu
 * lassen — das steht in keinem Verhältnis.
 */

// Klein gehalten: Ein Suchergebnis trägt bis zu 75 Treffer mit Titeln und Metadaten.
// Mehr als eine Handvoll Suchen hat niemand gleichzeitig im Kopf.
const MAX_EINTRAEGE = 8;

const eintraege = new Map();

/** Der Schlüssel einer Suche — Anfrage und Facetten, denn beide bestimmen das Ergebnis. */
export function suchSchluessel({ q = "", typ = "", fach = "", stufe = "" } = {}) {
  return JSON.stringify([q.trim(), typ, String(fach), String(stufe)]);
}

export function merken(schluessel, umschlag) {
  if (!schluessel || !umschlag) return;
  // Neu einfügen heißt ans Ende rücken: Ein Map behält die Einfügereihenfolge, damit
  // fällt beim Überlauf die am längsten ungenutzte Suche heraus.
  eintraege.delete(schluessel);
  eintraege.set(schluessel, umschlag);
  while (eintraege.size > MAX_EINTRAEGE) {
    eintraege.delete(eintraege.keys().next().value);
  }
}

/** Das gemerkte Ergebnis — oder `null`. Lesen frischt die Reihenfolge auf. */
export function holen(schluessel) {
  if (!eintraege.has(schluessel)) return null;
  const umschlag = eintraege.get(schluessel);
  eintraege.delete(schluessel);
  eintraege.set(schluessel, umschlag);
  return umschlag;
}

/** Für Tests und den Fall, dass jemand den Bestand nachweislich verändert hat. */
export function leeren() {
  eintraege.clear();
}
