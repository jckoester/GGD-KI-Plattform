/**
 * Welcher Assistent zu einem Einstieg passt — und in welcher Reihenfolge (0.15, Plan F7).
 *
 * Bis 0.14 nahm jeder Planungs-Einstieg „den ersten Assistenten mit `planning`" in der
 * Sortierreihenfolge. Mit dem Stundenassistenten und eigenen Assistenten der Lehrkräfte
 * wäre das Zufall. Die Regel hier ist fest — **kein Merken der letzten Wahl** (Jan,
 * 06.10.2026): Wer mehrere eigene Assistenten hat, hat sie vermutlich je Fach angelegt,
 * und das Fach der Stunde trifft dann den richtigen.
 *
 * Zwei Merkmale ergeben sechs Stufen. *Eigen* heißt selbst angelegt (`created_by`);
 * alles andere ist *fremd* — schulweit **oder** von einer Kollegin freigegeben:
 *
 * 1. eigen, Fach passend · 2. eigen, ohne Fach · 3. fremd, Fach passend ·
 * 4. fremd, ohne Fach · 5. eigen, Fach abweichend · 6. fremd, Fach abweichend.
 *
 * Innerhalb einer Stufe nach Name. Hat die Stunde kein Fach, gibt es kein „passend" —
 * Assistenten mit Fach stehen dann in 5 bzw. 6.
 *
 * ⚠️ **Gewählt wird aus der Menge, die die Person benutzen darf** (`GET /assistants`),
 * nicht aus einer Anzeigeliste. Was eine Darstellung verbirgt (`visibility: hidden`, eine
 * Sortierung aus Päckchen C), darf einen Einstieg nicht treffen — deshalb liest diese
 * Funktion `visibility` nicht.
 */

/** Wie die Fähigkeiten im Editor heißen — für Hinweise an Menschen. */
export const FAEHIGKEIT_NAMEN = {
  planning: "Unterrichtsplanung",
  lesson_planning: "Stundenplanung",
};

function stufe(assistent, pseudonym, fachId) {
  const eigen = pseudonym != null && assistent.created_by === pseudonym;
  if (assistent.subject_id == null) return eigen ? 2 : 4;
  if (fachId != null && assistent.subject_id === fachId) return eigen ? 1 : 3;
  return eigen ? 5 : 6;
}

/**
 * Die Kandidaten für einen Einstieg, bester zuerst. Leer, wenn keiner die Fähigkeit führt.
 *
 * @param {Array} assistenten — wie `GET /assistants` sie liefert
 * @param {string} faehigkeit — `planning` oder `lesson_planning`
 * @param {{pseudonym?: string|null, fachId?: number|null}} wer
 */
export function passendeAssistenten(assistenten, faehigkeit, { pseudonym = null, fachId = null } = {}) {
  return (assistenten ?? [])
    .filter((a) => Array.isArray(a.tool_groups) && a.tool_groups.includes(faehigkeit))
    .map((a) => ({ a, s: stufe(a, pseudonym, fachId) }))
    .sort((x, y) => x.s - y.s || (x.a.name ?? "").localeCompare(y.a.name ?? "", "de"))
    .map((x) => x.a);
}

/**
 * Welche Fähigkeit ein Einstieg sucht, wenn er keinen Assistenten nennt.
 *
 * Mit Stundenbezug die Stundenplanung (Entwurfsansicht, Startseite, ✦-Material); sonst die,
 * die der Einstieg **ausdrücklich** nennt (`faehigkeit=planning`: Jahresplaner,
 * Verschiebe-Auslöser). Eine Gruppe allein sucht nichts — „Neuer Chat" auf der Gruppenseite
 * ist ein gewöhnlicher Chat mit Gruppenbezug (0.15; bis dahin hieß „nur Gruppe" Jahresplanung).
 */
export function einstiegsFaehigkeit({ stundeId = null, faehigkeit = null } = {}) {
  if (stundeId != null) return "lesson_planning";
  return faehigkeit ?? null;
}
