// Rückkehr von der erneuten Anmeldung beim Schulkonto (Step-up, Redirect-Modus; 0.18.1).
//
// Der Browser verlässt die Seite und kommt per Weiterleitung zurück. Zwei Dinge gehen dabei
// verloren, wenn man sie nicht festhält:
//   - was schiefging: Das Backend hängt `stepup_fehler=<grund>` an die Ausgangsseite;
//   - was die Lehrkraft eingegeben hatte: Ein Formular merkt sich seine Eingaben vorher im
//     Sitzungsspeicher und holt sie danach einmal zurück.

export const STEPUP_FEHLER_PARAM = "stepup_fehler";

// Wie lange gemerkte Eingaben gelten. Die Anmeldung beim Schulkonto dauert Sekunden bis
// wenige Minuten; was älter ist, stammt aus einem abgebrochenen Versuch.
const GUELTIG_MS = 15 * 60 * 1000;

function uhrzeit(jetzt) {
  return jetzt.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

/** Der Satz zu einem Fehlercode aus dem Backend (`_stepup_abgelehnt`), oder null. */
export function stepupFehlerText(code, jetzt = new Date()) {
  if (!code) return null;
  const melden = `Scheitert es wieder, nennen Sie der Administration die Uhrzeit (${uhrzeit(jetzt)}) — dann lässt sich der Grund im Protokoll finden.`;
  switch (code) {
    case "abgebrochen":
      return "Die erneute Anmeldung wurde abgebrochen. Die Aktion wurde nicht ausgeführt.";
    case "anderes_konto":
      return "Sie haben sich mit einem anderen Konto angemeldet als dem, mit dem Sie hier arbeiten. Die Aktion wurde nicht ausgeführt.";
    case "ohne_2fa":
      return "Die erneute Anmeldung muss mit dem zweiten Faktor erfolgen (etwa dem Code aus der Authenticator-App). Die Aktion wurde nicht ausgeführt.";
    case "nicht_frisch":
      return `Die erneute Anmeldung ließ sich nicht bestätigen. Bitte versuchen Sie es noch einmal. ${melden}`;
    default:
      return `Die erneute Anmeldung ist fehlgeschlagen. Bitte versuchen Sie es noch einmal. ${melden}`;
  }
}

/** Ein Rücksprungziel aus der Adresse — nur lokale Pfade, sonst null (gegen Open-Redirect;
 *  dieselbe Regel wie `_safe_return_to` im Backend). */
export function lokalesZiel(wert) {
  if (!wert || !wert.startsWith("/") || ["/", "\\"].includes(wert[1])) return null;
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f]/.test(wert)) return null;
  return wert;
}

/** Fehlercode aus einem Query-String (`?…`), oder null. */
export function stepupFehlerAusUrl(search) {
  return new URLSearchParams(search).get(STEPUP_FEHLER_PARAM);
}

/** Pfad + Query ohne den Fehlercode — als Rücksprungziel und zum Aufräumen der Adresse. */
export function ohneStepupFehler(pathname, search) {
  const params = new URLSearchParams(search);
  params.delete(STEPUP_FEHLER_PARAM);
  const rest = params.toString();
  return rest ? `${pathname}?${rest}` : pathname;
}

/** Eingaben eines Formulars vor der Weiterleitung festhalten. */
export function merkeFormular(speicher, name, daten, jetztMs = Date.now()) {
  speicher.setItem(`stepup_formular:${name}`, JSON.stringify({ daten, zeit: jetztMs }));
}

/** Gemerkte Eingaben einmal zurückholen — danach sind sie weg. Null, wenn keine oder zu alt. */
export function holeFormular(speicher, name, jetztMs = Date.now()) {
  const schluessel = `stepup_formular:${name}`;
  const roh = speicher.getItem(schluessel);
  speicher.removeItem(schluessel);
  if (!roh) return null;
  try {
    const { daten, zeit } = JSON.parse(roh);
    if (typeof zeit !== "number" || jetztMs - zeit > GUELTIG_MS || jetztMs < zeit) return null;
    return daten ?? null;
  } catch {
    return null;
  }
}
