// Letzte Nachricht bearbeiten und Antwort abbrechen (0.19, Schritt 5).
//
// Bearbeiten ersetzt die letzte eigene Nachricht samt ihrer Antwort. Das Backend blendet
// beide aus (`ersetzt_letzte`), gelöscht wird nichts — an der alten Nachricht kann eine
// Krisenmeldung hängen (ADR-008).

/** Index der letzten eigenen Nachricht — oder -1. Was danach kommt (Antwort, Fehler,
 *  Trennlinie beim Assistentenwechsel), gehört zu ihr und fällt beim Ersetzen mit weg. */
export function letzteEigeneIndex(messages) {
  for (let i = (messages?.length ?? 0) - 1; i >= 0; i--) {
    if (messages[i]?.role === "user") return i;
  }
  return -1;
}

/** Ist die Nachricht an `index` die, die sich bearbeiten lässt? */
export function istBearbeitbar(messages, index, { isStreaming = false, conversationId = null } = {}) {
  return !isStreaming && conversationId != null && index === letzteEigeneIndex(messages);
}

// Die schreibenden Werkzeuge (`ChatTool.writes`) — Stand 0.19. Ein unbekannter Name wird
// zu „etwas geändert", der Hinweis fällt also nie still weg.
const PLAN = "die Jahresplanung geändert";
const WIRKUNGEN = {
  update_lesson_phases: "den Stundenentwurf geändert",
  create_lessons: "Stundenentwürfe angelegt",
  waehle_stunde: "eine Stunde gewählt oder angelegt",
  apply_plan_operations: PLAN,
  assign_slots_to_unit: PLAN,
  create_teaching_unit: PLAN,
  set_slot_category: PLAN,
  set_slot_topics: PLAN,
  undo_last_change: PLAN,
  generate_image: "ein Bild erzeugt",
};

/**
 * Was die Antwort, die ersetzt würde, schon bewirkt hat — als Satz, oder null.
 * Ein Bild zählt auch ohne Werkzeugnamen: Es steht in der Bibliothek.
 */
export function wirkungsHinweis(antwort) {
  if (!antwort) return null;
  const teile = (antwort.werkzeuge_mit_wirkung ?? []).map((w) => WIRKUNGEN[w] ?? "etwas geändert");
  if (antwort.images?.length && !teile.includes(WIRKUNGEN.generate_image)) teile.push(WIRKUNGEN.generate_image);
  const eindeutig = [...new Set(teile)];
  if (!eindeutig.length) return null;
  return `Die bisherige Antwort hat ${eindeutig.join(" und ")}. Das bleibt bestehen — `
    + "zurücknehmen lässt es sich über den Verlauf der Planung bzw. in der Bibliothek.";
}

/** Hatte die Nachricht Anhänge? Deren Inhalt lebt nur im Browser und muss neu hinzu. */
export function hatteAnhaenge(nachricht) {
  return Boolean(nachricht?.uploadedAttachments?.length || nachricht?.attachments?.length);
}

/** Wurde der Strom absichtlich abgebrochen (Stopp-Knopf)? */
export function istAbbruch(fehler, signal) {
  return Boolean(signal?.aborted) || fehler?.name === "AbortError";
}
