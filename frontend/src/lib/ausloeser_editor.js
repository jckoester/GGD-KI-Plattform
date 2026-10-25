/**
 * Auslöser-Beispiele im Assistenten-Editor (Päckchen C1, Schritt 4).
 *
 * Im Formular steht je Liste **ein Text mit einem Eintrag pro Zeile** — das lässt sich
 * schreiben, einfügen und vergleichen wie jedes andere Feld. Erst beim Speichern wird daraus
 * die Liste, die der Server erwartet (`trigger_examples`/`trigger_counterexamples`).
 *
 * ⚠️ Die Grenzen spiegeln `app/assistants/ausloeser.py` (`MAX_EINTRAEGE`, `MAX_ZEICHEN`).
 * Der Server prüft selbst; hier geht es nur darum, es vor dem Speichern zu sagen.
 */

export const EMPFOHLEN_MIN = 5;
export const EMPFOHLEN_MAX = 15;
export const MAX_EINTRAEGE = 30;
export const MAX_ZEICHEN = 500;

/** Zeilen → Liste: Rand weg, leere Zeilen weg, Dubletten weg (wie der Server). */
export function zeilenZuListe(text) {
  const liste = [];
  for (const zeile of String(text ?? "").split("\n")) {
    const t = zeile.trim();
    if (t && !liste.includes(t)) liste.push(t);
  }
  return liste;
}

/** Liste → Zeilen. `null` heißt „nicht geladen“ und ergibt ein leeres Feld. */
export function listeZuZeilen(liste) {
  return (liste ?? []).join("\n");
}

/**
 * Was unter einer Liste steht: Zähler und, falls nötig, eine Warnung.
 * `art`: "beispiel" | "gegenbeispiel"; `suggest`: "specific" | "fallback" | "never".
 */
export function listenHinweis(text, art, suggest) {
  const liste = zeilenZuListe(text);
  const n = liste.length;
  const wort = art === "beispiel" ? (n === 1 ? "Beispiel" : "Beispiele")
                                  : (n === 1 ? "Gegenbeispiel" : "Gegenbeispiele");
  const zaehler = `${n} ${wort} · empfohlen ${EMPFOHLEN_MIN}–${EMPFOHLEN_MAX}`;

  const zuLang = liste.find((t) => t.length > MAX_ZEICHEN);
  if (n > MAX_EINTRAEGE)
    return { zaehler, fehler: `Höchstens ${MAX_EINTRAEGE} Einträge.` };
  if (zuLang)
    return { zaehler, fehler: `Höchstens ${MAX_ZEICHEN} Zeichen je Zeile („${zuLang.slice(0, 30)}…“).` };

  if (art === "beispiel" && suggest !== "never") {
    if (n === 0)
      return { zaehler, warnung: "Ohne Beispiele wird der Assistent nicht vorgeschlagen." };
    if (n < EMPFOHLEN_MIN)
      return { zaehler, warnung: `Mit weniger als ${EMPFOHLEN_MIN} Beispielen trifft der Vorschlag unsicher.` };
  }
  if (n > EMPFOHLEN_MAX)
    return { zaehler, warnung: `Mehr als ${EMPFOHLEN_MAX} Einträge machen den Vergleich nicht genauer, nur breiter.` };
  return { zaehler };
}
