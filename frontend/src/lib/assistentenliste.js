/**
 * Welche Assistenten eine **Anzeigeliste** zeigt (0.22, Päckchen C1, F3).
 *
 * `visibility: hidden` heißt: nicht in Übersicht, Auswahl und (später) Vorschlag — aber
 * benutzbar über Link (`/chat?assistant_id=`), Einstieg und Chat. Deshalb filtert hier die
 * **Darstellung**, nicht die Zugangsregel (`backend/app/assistants/sichtbarkeit.py`), und
 * die Einstiege (`assistentenwahl.js`) wählen weiter aus der vollen Liste.
 *
 * `private` als Sichtbarkeit gibt es seit 0.22 nicht mehr — das Modell speichert es als
 * `hidden` (Jan, 25.10.2026). Ein Altbestand mit `private` wird hier ebenso verborgen.
 *
 * @param {Array<{visibility?: string}>|null|undefined} liste
 */
export function zurAnzeige(liste) {
  return (liste ?? []).filter((a) => a?.visibility !== "hidden" && a?.visibility !== "private");
}

/**
 * Die Rückfall-Assistenten eines Fachs (0.26, F37 b): `suggest: fallback`, und ihre `tags` nennen
 * das Fach. Rückfälle haben kein `subject_id` — sie gehören zu einer Tätigkeit, nicht zu einem
 * Fach —, deshalb erschienen sie bis dahin auf keiner Fach- oder Gruppenseite.
 *
 * @param {Array<{suggest?: string, tags?: string[]|null}>|null|undefined} liste
 * @param {string|null|undefined} slug  Slug des Fachs (`chemie`)
 */
export function allgemeineImFach(liste, slug) {
  if (!slug) return [];
  return (liste ?? []).filter((a) => a?.suggest === "fallback" && (a.tags ?? []).includes(slug));
}

/**
 * Reihenfolge der Chat-Auswahl mit Fachbezug: zuerst die Assistenten des Fachs, dann die
 * allgemeinen Assistenten des Fachs, dann alle übrigen. ``abschnitte`` nennt, wo ein
 * Zwischentitel steht: vor den allgemeinen immer, vor den übrigen, wenn etwas davor steht.
 *
 * @param {Array<{id: number, subject_id?: number|null}>} liste
 * @param {number|null|undefined} subjectId
 * @param {string|null|undefined} slug
 * @returns {{liste: Array, abschnitte: Array<{index: number, titel: string}>}}
 */
export function ordneFuerFach(liste, subjectId, slug) {
  const alle = liste ?? [];
  if (subjectId == null) return { liste: alle, abschnitte: [] };
  const fach = alle.filter((a) => a.subject_id === subjectId);
  const allgemein = allgemeineImFach(alle, slug).filter((a) => !fach.includes(a));
  const rest = alle.filter((a) => !fach.includes(a) && !allgemein.includes(a));
  const abschnitte = [];
  if (allgemein.length) abschnitte.push({ index: fach.length, titel: "Allgemeine Assistenten" });
  if (rest.length && (fach.length || allgemein.length)) {
    abschnitte.push({ index: fach.length + allgemein.length, titel: "Weitere Assistenten" });
  }
  return { liste: [...fach, ...allgemein, ...rest], abschnitte };
}
