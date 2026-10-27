/**
 * Logik der Fach-Mehrfachauswahl (Chips + Suchfeld, `FachMehrfachauswahl.svelte`).
 *
 * Ausgelagert, weil das Projekt keine Komponententests hat (siehe `picker_tastatur.test.js`):
 * Was hier steht, prüfen die Logiktests; die Komponente verdrahtet nur.
 *
 * Zuerst gebraucht für „Operatoren aus diesen Fächern" am Assistenten (Päckchen AF, 0.23).
 */

/**
 * Die Fächer, die das Suchfeld vorschlägt: noch nicht gewählt, Name oder Slug enthält die
 * Eingabe. Treffer am Wortanfang zuerst („ch" → Chemie vor Geschichte), sonst in der
 * gelieferten Reihenfolge.
 *
 * @param {{slug: string, name: string}[]} faecher
 * @param {string[]} gewaehlt Slugs
 * @param {string} eingabe
 * @returns {{slug: string, name: string}[]}
 */
export function vorschlaege(faecher, gewaehlt, eingabe) {
  const q = (eingabe || "").trim().toLowerCase();
  const frei = (faecher || []).filter((f) => !(gewaehlt || []).includes(f.slug));
  if (!q) return frei;
  const passt = frei.filter(
    (f) => f.name.toLowerCase().includes(q) || f.slug.toLowerCase().includes(q),
  );
  const amAnfang = (f) =>
    f.name.toLowerCase().split(/[\s-]+/).some((w) => w.startsWith(q)) ? 0 : 1;
  return passt
    .map((f, i) => [f, i])
    .sort(([a, i], [b, j]) => amAnfang(a) - amAnfang(b) || i - j)
    .map(([f]) => f);
}

/** Ein Slug dazu — ohne Dublette, ans Ende. */
export function hinzu(gewaehlt, slug) {
  const liste = gewaehlt || [];
  return liste.includes(slug) ? liste : [...liste, slug];
}

/** Ein Slug weg. */
export function weg(gewaehlt, slug) {
  return (gewaehlt || []).filter((s) => s !== slug);
}

/**
 * Anzeigename eines gewählten Slugs. Ein Slug, den es hier nicht (mehr) gibt, bleibt als
 * Chip sichtbar — still verschwinden darf er nicht, sonst ginge er beim Speichern verloren,
 * ohne dass es jemand merkt.
 */
export function anzeige(faecher, slug) {
  const f = (faecher || []).find((x) => x.slug === slug);
  return f ? { name: f.name, color: f.color ?? null, bekannt: true } : { name: slug, color: null, bekannt: false };
}

/**
 * Nächster Fokus in der Vorschlagsliste: Pfeiltasten laufen im Kreis, -1 heißt „keiner".
 */
export function naechsterFokus(fokus, anzahl, richtung) {
  if (anzahl <= 0) return -1;
  if (fokus < 0) return richtung > 0 ? 0 : anzahl - 1;
  return (fokus + richtung + anzahl) % anzahl;
}
