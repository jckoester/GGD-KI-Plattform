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
 * Bildungsplan-Fassung über den Jahrgang und die Einordnung in der Historie (bis 0.23 auch
 * das Werkzeug `get_operatoren`, das ohne Fach gar nicht antwortete). Wer von der Fachseite kam,
 * bekam also eine **schlechtere** Suche als über den Umweg „Chat öffnen, Fach von Hand
 * wählen".
 *
 * Deshalb stehen beide Richtungen hier nebeneinander: Ein Parameter, den nur eine Seite
 * kennt, ist kein Parameter.
 */

/**
 * Der Pfad für einen neuen Chat mit Vorbelegung.
 *
 * `stundeId` ist der Stundenbezug (0.15): die Kennung einer Unterrichtsstunde. Der Server
 * leitet daraus die Gruppe ab; eine mitgegebene `groupId` muss dazu passen.
 *
 * `faehigkeit` (→ `faehigkeit`): Der Einstieg will einen Assistenten mit dieser Fähigkeit,
 * nennt aber keinen bestimmten — die Chatseite wählt ihn (`$lib/assistentenwahl.js`). Die
 * Planungs-Einstiege setzen `planning`. ⚠️ **Ausdrücklich, nicht aus der Gruppe geschlossen**
 * (0.15): Bis dahin hieß „nur `group_id`" die Jahresplanung — ein „Neuer Chat" auf der
 * Gruppenseite hätte so die Jahresplanung geöffnet, bei Schüler:innen den Hinweis „kein
 * Assistent verfügbar". Ein Chat mit Gruppenbezug ist zuerst ein Chat.
 *
 * `assistantId` (→ `assistant_id`) und `frage` (→ `q`) liest die Chatseite seit jeher
 * selbst; hier stehen sie, damit ein Einstieg den ganzen Pfad an einer Stelle baut.
 */
export function neuerChatPfad({
  subjectId = null, groupId = null, stundeId = null, assistantId = null, frage = null,
  faehigkeit = null,
} = {}) {
  const params = new URLSearchParams();
  if (subjectId != null) params.set("subject_id", String(subjectId));
  if (groupId != null) params.set("group_id", String(groupId));
  if (stundeId != null) params.set("stunde_id", String(stundeId));
  if (assistantId != null) params.set("assistant_id", String(assistantId));
  if (faehigkeit) params.set("faehigkeit", faehigkeit);
  if (frage) params.set("q", frage);
  const query = params.toString();
  return query ? `/chat?${query}` : "/chat";
}

const UUID_FORM = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Fähigkeiten, nach denen ein Einstieg fragen darf — andere Werte gelten als nicht genannt. */
const EINSTIEGS_FAEHIGKEITEN = new Set(["planning", "lesson_planning"]);

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
  const roheStunde = searchParams?.get?.("stunde_id");
  const roheFaehigkeit = searchParams?.get?.("faehigkeit");
  return {
    subjectId: zahl("subject_id"),
    groupId: zahl("group_id"),
    stundeId: roheStunde && UUID_FORM.test(roheStunde) ? roheStunde : null,
    faehigkeit: EINSTIEGS_FAEHIGKEITEN.has(roheFaehigkeit) ? roheFaehigkeit : null,
  };
}
