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
