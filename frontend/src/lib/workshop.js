/** Reine Helfer für die Material-Werkstatt (Phase 19). */

/**
 * Leitet einen Dokumenttitel aus Markdown ab: erste Überschrift, sonst erste nicht-leere
 * Zeile (ohne Markup-Rauschen), sonst „Arbeitsblatt". Auf 80 Zeichen gekürzt.
 */
export function deriveDocTitle(markdown) {
    const lines = (markdown || '').split('\n');
    const heading = lines.find((l) => /^#{1,6}\s+/.test(l));
    if (heading) {
        return heading.replace(/^#{1,6}\s+/, '').trim().slice(0, 80) || 'Arbeitsblatt';
    }
    const first = lines.find((l) => l.trim());
    if (!first) return 'Arbeitsblatt';
    // Führendes Listen-/Zitat-Markup entfernen für einen sauberen Titel.
    return first.replace(/^\s*([-*+>]|\d+\.)\s+/, '').trim().slice(0, 80) || 'Arbeitsblatt';
}

/**
 * Was die Übernahme einer Antwort mitnimmt — und was nicht.
 *
 * Werkstatt und Bausteinübernahme legen beide ein **Markdown-Dokument** an; sie
 * bekommen `message.content` und sonst nichts. Ein erzeugtes Bild ist kein Text und
 * bleibt deshalb zurück.
 *
 * ⚠️ Der stille Verlust, den das sichtbar macht: Bei einer Bildantwort schreibt das
 * Modell meist einen Satz dazu („Hier ist dein Bild:"). Der Knopf erschien also,
 * das Dokument bestand aus dieser einen Zeile, und das Bild war weg — ohne dass
 * irgendwo stand, dass es so gemeint war.
 *
 * Der Knopf bleibt trotzdem: Eine ausführliche Erklärung mit illustrierendem Bild
 * ist ein berechtigter Fall, und „Bildunterschrift" von „Erklärung" zu
 * unterscheiden hieße raten (eine Längenschwelle wäre genau das).
 *
 * @param {{images?: Array}|null} message
 * @returns {string|null} Zusatz für den Tooltip, oder `null`
 */
export function nurTextHinweis(message) {
    if (!message?.images?.length) return null;
    return (
        "Übernimmt nur den Text dieser Antwort. Das Bild speicherst du mit dem " +
        "Knopf am Bild."
    );
}
