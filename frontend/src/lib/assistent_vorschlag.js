/**
 * Assistenten-Vorschlag im Chat (Päckchen C2, 0.24) — was die Oberfläche daraus macht.
 *
 * Der Server schickt nach der Antwort das Ereignis `vorschlag` mit Optionen (spezifisch,
 * Rückfall, beenden). Hier steht, wann der Dialog sichtbar ist und was eine Wahl auslöst; die
 * Chatseite verdrahtet nur (keine Komponententests im Projekt, siehe `picker_tastatur.test.js`).
 */
import { hatteAnhaenge, letzteEigeneIndex } from "./chat_bearbeiten.js";

/** Beschriftung einer Option. */
export function beschriftung(option) {
  if (option.art === "beenden") return "Assistent beenden und weiter chatten";
  return `Assistent für ${option.name}`;
}

/** Der Einleitungssatz: Beim Beenden allein geht es um die Frage, sonst um die Aufgabe. */
export function einleitung(optionen) {
  const nurBeenden = (optionen || []).every((o) => o.art === "beenden");
  return nurBeenden
    ? "Diese Frage gehört nicht zu diesem Assistenten."
    : "Für diese Aufgabe gibt es einen Assistenten, der dich Schritt für Schritt begleitet.";
}

/**
 * Ist der Dialog an der Nachricht `index` zu zeigen? Nur an der **letzten** Antwort und nicht,
 * solange eine neue läuft: Schreibt die Schüler:in weiter, verfällt der Vorschlag.
 */
export function sichtbar(messages, index, isStreaming) {
  const m = messages?.[index];
  if (!m?.vorschlag?.length || isStreaming) return false;
  return index > letzteEigeneIndex(messages);
}

/**
 * Was eine Wahl bewirkt. `neuBeantworten`: Die letzte eigene Nachricht wird neu geschickt
 * (`ersetzt_letzte`) — außer sie hatte Anhänge; dann gilt der Wechsel ab der nächsten Nachricht.
 */
export function wahl(option, messages, assistenten = []) {
  const index = letzteEigeneIndex(messages);
  const letzte = index >= 0 ? messages[index] : null;
  const beenden = option.art === "beenden";
  return {
    beenden,
    assistent: beenden
      ? null
      : assistenten.find((a) => a.id === option.assistant_id) ?? { id: option.assistant_id, name: option.name },
    neuBeantworten: Boolean(letzte) && !hatteAnhaenge(letzte),
    index,
    text: letzte?.content ?? "",
  };
}
