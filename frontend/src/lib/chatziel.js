/**
 * Was ein Link „Neuer Chat" mitgibt — und was die Chatseite davon liest.
 *
 * ⚠️ **Zwei Seiten, eine Absprache, und sie war einseitig** (Jan, 26.09.2026): Der
 * Knopf auf der Fachseite rief `goto("/chat")` ohne jeden Parameter, und
 * `pendingSubjectId` auf der Chatseite wurde von **keinem** URL-Parameter befüllt —
 * obwohl der Zustand dafür längst da war. Wer von der Fachseite aus chattete, bekam
 * eine Unterhaltung ohne Fachbezug.
 *
 * **Die Folgen sind größer, als es aussieht.** Am Fach hängen der Fachbonus der Suche
 * (er entscheidet messbar über die Reihenfolge der Treffer), die Wahl der
 * Bildungsplan-Fassung über den Jahrgang, das Werkzeug `get_operatoren` (das ohne Fach
 * gar nicht antwortet) und die Einordnung in der Historie. Wer von der Fachseite kam,
 * bekam also eine **schlechtere** Suche als über den Umweg „Chat öffnen, Fach von Hand
 * wählen".
 *
 * Deshalb stehen beide Richtungen hier nebeneinander: Ein Parameter, den nur eine Seite
 * kennt, ist kein Parameter.
 */

/** Der Pfad für einen neuen Chat mit Vorbelegung. */
export function neuerChatPfad({ subjectId = null, groupId = null } = {}) {
  const params = new URLSearchParams();
  if (subjectId != null) params.set("subject_id", String(subjectId));
  if (groupId != null) params.set("group_id", String(groupId));
  const query = params.toString();
  return query ? `/chat?${query}` : "/chat";
}

/**
 * Die Vorbelegung aus der Adresse — `null`, wo nichts steht.
 *
 * Unbrauchbare Werte (`?subject_id=abc`) werden zu `null`: Ein `NaN` im Zustand
 * erreichte den Server als `null` und wäre dort nicht von „nicht angegeben" zu
 * unterscheiden — nur dass unterwegs niemand mehr weiß, dass etwas dastand.
 */
export function chatVorgaben(searchParams) {
  const zahl = (name) => {
    const roh = searchParams?.get?.(name);
    if (!roh) return null;
    const wert = Number.parseInt(roh, 10);
    return Number.isNaN(wert) ? null : wert;
  };
  return { subjectId: zahl("subject_id"), groupId: zahl("group_id") };
}
