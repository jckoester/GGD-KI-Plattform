/**
 * Logik der Chip-Auswahl (gewählte Einträge als Chips + Suchfeld, `ChipAuswahl.svelte`).
 *
 * Ausgelagert, weil das Projekt keine Komponententests hat (siehe `picker_tastatur.test.js`):
 * Was hier steht, prüfen die Logiktests; die Komponente verdrahtet nur.
 *
 * Ein Eintrag ist `{ wert, name, color? }` — `wert` ist, was gespeichert wird (Fach-Slug,
 * Assistenten-ID), `name`, was man liest. Nutzer: „Operatoren aus diesen Fächern“ (Päckchen AF,
 * 0.23) und die Rückfall-Assistenten eines Vorschlags (C2, 0.24).
 */

/**
 * Die Einträge, die das Suchfeld vorschlägt: noch nicht gewählt, Name (oder Wert, wenn er ein
 * Text ist) enthält die Eingabe. Treffer am Wortanfang zuerst („ch" → Chemie vor Geschichte),
 * sonst in der gelieferten Reihenfolge.
 *
 * @param {{wert: string|number, name: string}[]} eintraege
 * @param {(string|number)[]} gewaehlt
 * @param {string} eingabe
 */
export function vorschlaege(eintraege, gewaehlt, eingabe) {
  const q = (eingabe || "").trim().toLowerCase();
  const frei = (eintraege || []).filter((e) => !(gewaehlt || []).includes(e.wert));
  if (!q) return frei;
  const passt = frei.filter(
    (e) => e.name.toLowerCase().includes(q) || String(e.wert).toLowerCase().includes(q),
  );
  const amAnfang = (e) =>
    e.name.toLowerCase().split(/[\s-]+/).some((w) => w.startsWith(q)) ? 0 : 1;
  return passt
    .map((e, i) => [e, i])
    .sort(([a, i], [b, j]) => amAnfang(a) - amAnfang(b) || i - j)
    .map(([e]) => e);
}

/** Ein Wert dazu — ohne Dublette, ans Ende. */
export function hinzu(gewaehlt, wert) {
  const liste = gewaehlt || [];
  return liste.includes(wert) ? liste : [...liste, wert];
}

/** Ein Wert weg. */
export function weg(gewaehlt, wert) {
  return (gewaehlt || []).filter((w) => w !== wert);
}

/**
 * Anzeigename eines gewählten Werts. Ein Wert, den es hier nicht (mehr) gibt, bleibt als Chip
 * sichtbar — still verschwinden darf er nicht, sonst ginge er beim Speichern verloren, ohne
 * dass es jemand merkt.
 */
export function anzeige(eintraege, wert) {
  const e = (eintraege || []).find((x) => x.wert === wert);
  return e
    ? { name: e.name, color: e.color ?? null, bekannt: true }
    : { name: String(wert), color: null, bekannt: false };
}

/** Nächster Fokus in der Vorschlagsliste: Pfeiltasten laufen im Kreis, -1 heißt „keiner". */
export function naechsterFokus(fokus, anzahl, richtung) {
  if (anzahl <= 0) return -1;
  if (fokus < 0) return richtung > 0 ? 0 : anzahl - 1;
  return (fokus + richtung + anzahl) % anzahl;
}

/** Fächer (`{slug, name, color}`) als Einträge. */
export function faecherAlsEintraege(faecher) {
  return (faecher || []).map((f) => ({ wert: f.slug, name: f.name, color: f.color ?? null }));
}
