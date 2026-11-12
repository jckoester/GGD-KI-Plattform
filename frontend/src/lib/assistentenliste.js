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

/** Wie viele Schlagwörter eine Assistentenkarte zeigt (0.26, F37 a). */
export const SCHLAGWOERTER_MAX = 3;

/**
 * Schlagwörter einer Karte zum Anzeigen (0.26, F37 a): Ein Schlagwort, das ein Fach-Slug ist,
 * erscheint mit dem Fachnamen („religion-ev“ → „Evangelische Religion“); andere Schlagwörter
 * bleiben, wie sie sind. Höchstens ``max``, der Rest als Zahl und Liste für den Tooltip.
 *
 * @param {string[]|null|undefined} tags
 * @param {Array<{slug: string, name: string}>} faecher
 * @returns {{namen: string[], mehr: string[]}}
 */
export function schlagwoerterAnzeige(tags, faecher, max = SCHLAGWOERTER_MAX) {
  const nachSlug = Object.fromEntries((faecher ?? []).map((f) => [f.slug, f.name]));
  const namen = [...new Set((tags ?? []).map((t) => nachSlug[t] ?? t))];
  return { namen: namen.slice(0, max), mehr: namen.slice(max) };
}

/**
 * Abschnitte der Übersicht `/assistants` (0.26, F37 c): „Für bestimmte Aufgaben“ (`suggest:
 * specific`), „Allgemein“ (`fallback`), dann „Weitere Assistenten“ (alles andere — etwa Assistenten
 * für Lehrkräfte oder eigene, die nicht vorgeschlagen werden). Leere Abschnitte entfallen;
 * ``titel`` ist ``null``, wenn nur ein Abschnitt übrig bleibt — eine einzelne Überschrift
 * gliedert nichts.
 *
 * @param {Array<{suggest?: string|null}>} liste
 * @returns {Array<{titel: string|null, liste: Array}>}
 */
export function abschnitteUebersicht(liste) {
  const alle = liste ?? [];
  const abschnitte = [
    { titel: "Für bestimmte Aufgaben", liste: alle.filter((a) => a?.suggest === "specific") },
    { titel: "Allgemein", liste: alle.filter((a) => a?.suggest === "fallback") },
    { titel: "Weitere Assistenten", liste: alle.filter((a) => a?.suggest !== "specific" && a?.suggest !== "fallback") },
  ].filter((a) => a.liste.length > 0);
  return abschnitte.length > 1 ? abschnitte : abschnitte.map((a) => ({ ...a, titel: null }));
}

/**
 * Klassenstufen als Bereiche: `[5, 6, 7, 9, 10]` → „5–7, 9–10“.
 * @param {number[]} stufen
 */
export function stufenBereiche(stufen) {
  const s = [...new Set(stufen ?? [])].sort((a, b) => a - b);
  const teile = [];
  for (let i = 0; i < s.length; i++) {
    let j = i;
    while (j + 1 < s.length && s[j + 1] === s[j] + 1) j++;
    teile.push(i === j ? `${s[i]}` : `${s[i]}–${s[j]}`);
    i = j;
  }
  return teile.join(", ");
}

/**
 * Hinweis für Admins: Assistenten, die wegen fehlender Modell-Freischaltung für einen Teil
 * ihrer Zielgruppe unsichtbar sind (0.27, `GET /admin/assistants/model-check`, `gesperrt`).
 * Zusammengefasst nach Modell und Stufen, sonst stünden 14 fast gleiche Zeilen untereinander.
 *
 * @param {Array<{name: string, model: string, stufen: number[], lehrkraefte: boolean}>} gesperrt
 * @returns {string|null}
 */
export function gesperrtHinweis(gesperrt) {
  if (!gesperrt?.length) return null;
  const gruppen = new Map();
  for (const g of gesperrt) {
    const wer = [g.stufen?.length ? `Kl. ${stufenBereiche(g.stufen)}` : null, g.lehrkraefte ? "Lehrkräfte" : null]
      .filter(Boolean).join(", ");
    const schluessel = `${g.model} · ${wer}`;
    gruppen.set(schluessel, [...(gruppen.get(schluessel) ?? []), `„${g.name}“`]);
  }
  const teile = [...gruppen].map(([schluessel, namen]) => `${schluessel}: ${namen.join(", ")}`);
  const anzahl = gesperrt.length === 1 ? "Ein Assistent ist" : `${gesperrt.length} Assistenten sind`;
  return `${anzahl} für einen Teil ihrer Zielgruppe unsichtbar, weil ihr Modell dort nicht freigeschaltet ist — ${teile.join("; ")}. Freischalten unter Einstellungen → Modell-Freischaltung.`;
}

/**
 * Klassenstufen eines Assistenten als kurze Angabe — „Kl. 8–13“, „ab Kl. 8“, „bis Kl. 7“,
 * „Kl. 9“; leer ohne Grenzen (0.27: sichtbar in Verwaltung, Freigabe und auf Karten).
 * @param {{min_grade?: number|null, max_grade?: number|null}} a
 */
export function stufenText(a) {
  const von = a?.min_grade ?? null, bis = a?.max_grade ?? null;
  if (von == null && bis == null) return "";
  if (von != null && bis != null) return von === bis ? `Kl. ${von}` : `Kl. ${von}–${bis}`;
  return von != null ? `ab Kl. ${von}` : `bis Kl. ${bis}`;
}

// ── Werkzeuge: Angabe „stellt her“ (0.40, Päckchen AM) ──────────────────────
//
// Ein Werkzeug ist ein Assistent mit Angabe `produces`. Die Arten (Kennung, Marke,
// Filterbeschriftung) kommen vom Backend (`$lib/produktarten.js`); hier stehen nur die
// reinen Handgriffe für Marke, Filter und Adresse (`?erstellt=`).

/** Wert von `?erstellt=` für „alle Werkzeuge“. */
export const ALLE_WERKZEUGE = "alle";

/**
 * Die Marken eines Assistenten, in Listenreihenfolge. Unbekannte Kennungen fallen weg.
 *
 * @param {{produces?: string[]}} assistent
 * @param {Array<{id: string, marke: string}>} arten
 */
export function markenVon(assistent, arten) {
  const gesetzt = new Set(assistent?.produces ?? []);
  return (arten ?? []).filter((a) => gesetzt.has(a.id)).map((a) => a.marke);
}

/**
 * Die Arten, die in der Liste tatsächlich vorkommen — nur sie bekommen einen Filter.
 *
 * @param {Array<{produces?: string[]}>} liste
 * @param {Array<{id: string}>} arten
 */
export function filterArten(liste, arten) {
  const vorhanden = new Set((liste ?? []).flatMap((a) => a?.produces ?? []));
  return (arten ?? []).filter((a) => vorhanden.has(a.id));
}

/**
 * Der gültige Filter aus der Adresse: `null` (alle Assistenten), `"alle"` (alle Werkzeuge)
 * oder eine Kennung. Unbekanntes zählt als `null` — ein alter Link zeigt dann alles statt nichts.
 *
 * @param {string|null|undefined} wert  `?erstellt=`
 * @param {Array<{id: string}>} arten
 */
export function erstelltFilter(wert, arten) {
  if (wert === ALLE_WERKZEUGE) return ALLE_WERKZEUGE;
  return (arten ?? []).some((a) => a.id === wert) ? wert : null;
}

/**
 * Liste nach Filter.
 *
 * @param {Array<{produces?: string[]}>} liste
 * @param {string|null} filter  aus `erstelltFilter`
 */
export function nachErstellt(liste, filter) {
  if (!filter) return liste ?? [];
  return (liste ?? []).filter((a) => {
    const p = a?.produces ?? [];
    return filter === ALLE_WERKZEUGE ? p.length > 0 : p.includes(filter);
  });
}
