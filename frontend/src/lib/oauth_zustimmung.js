/**
 * Zustimmungsseite für KI-Programme (0.55, Päckchen AX Schritt 4) — die Logik ohne Oberfläche.
 *
 * Ohne Sitzung führt die Seite zur Anmeldung und kommt danach mit derselben Anfrage zurück
 * (`/?return_to=…`, nur lokale Pfade — dieselbe Regel wie beim „Kurz neu anmelden“).
 */

/** Die Anfrage aus der Adresse, oder null. */
export function anfrageAusUrl(search) {
  const anfrage = new URLSearchParams(search).get("anfrage");
  return anfrage && anfrage.trim() ? anfrage.trim() : null;
}

/** Wohin ohne Anmeldung: zur Anmeldeseite, mit Rücksprung auf genau diese Zustimmung. */
export function anmeldeZiel(anfrage) {
  const zurueck = `/oauth/consent?anfrage=${encodeURIComponent(anfrage)}`;
  return `/?return_to=${encodeURIComponent(zurueck)}`;
}

/** Meldung für einen Fehler beim Laden — je nach Status. */
export function fehlerText(status, detail) {
  if (status === 403) return "KI-Programme verbinden können nur Lehrkräfte und Admins.";
  if (status === 404) return "Die Schnittstelle für KI-Programme ist an dieser Schule nicht eingeschaltet.";
  return detail || "Die Anfrage ließ sich nicht laden. Bitte im Programm neu verbinden.";
}
