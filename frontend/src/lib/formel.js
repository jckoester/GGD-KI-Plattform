/**
 * Formeln im Eingabefeld des Chats (0.38): finden, einsetzen, bereinigen.
 *
 * Die Nachricht bleibt Text. Der Formel-Dialog setzt seine Formel als `\(…\)` an die
 * Cursorstelle; steht der Cursor schon in einer Formel, ersetzt er genau diese. Erkannt
 * werden dieselben Begrenzer, die `markdown.js` rendert — auch selbst getipptes `$…$`.
 */

// Wie `matchDisplayMath`/`matchInlineMath` in markdown.js, hier als globale Suche.
// Reihenfolge zählt: `$$` vor `$`.
const FORMEL = /\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$|\$(?![\s$])((?:\\.|[^$\\\n])+?)\$(?!\d)/g;

/**
 * Die Formel, in der der Cursor steht (Begrenzer eingeschlossen), oder `null`.
 * Ein Cursor direkt vor oder hinter den Begrenzern zählt mit — dorthin setzt man ihn,
 * wenn man auf eine Formel zeigt.
 *
 * @returns {{start: number, ende: number, tex: string, abgesetzt: boolean} | null}
 */
export function formelAmCursor(text, pos) {
    for (const m of String(text ?? '').matchAll(FORMEL)) {
        const start = m.index;
        const ende = start + m[0].length;
        if (pos < start) return null;
        if (pos <= ende) {
            const tex = m[1] ?? m[2] ?? m[3] ?? m[4];
            return { start, ende, tex, abgesetzt: m[2] !== undefined || m[3] !== undefined };
        }
    }
    return null;
}

/**
 * Setzt `tex` in den Text: über `bereich` (eine Formel oder eine Auswahl) oder an der
 * Cursorstelle. Leeres `tex` über einer Formel entfernt sie.
 *
 * @param {string} text
 * @param {{start: number, ende: number}} bereich
 * @param {string} tex
 * @param {boolean} [abgesetzt] `\[…\]` statt `\(…\)`
 * @returns {{text: string, cursor: number}}
 */
export function formelEinsetzen(text, bereich, tex, abgesetzt = false) {
    const vorne = text.slice(0, bereich.start);
    const hinten = text.slice(bereich.ende);
    const formel = tex ? (abgesetzt ? `\\[${tex}\\]` : `\\(${tex}\\)`) : '';
    return { text: vorne + formel + hinten, cursor: vorne.length + formel.length };
}

// MathLive kennt Befehle, die KaTeX nicht kennt. `latex-expanded` löst die meisten auf
// (`\exponentialE` → `\mathrm{e}`); der Rest aus der Bildschirmtastatur steht hier
// (Versuch 08.11.2026: 267 Tasten gegen KaTeX geprüft).
const ERSATZ = [
    [/\\doubleprime\b/g, '\\prime\\prime'],
    [/\\nsubset\b/g, '\\not\\subset'],
    [/\\nsupset\b/g, '\\not\\supset'],
    [/\\biconditional\b/g, '\\leftrightarrow'],
    [/\\roundimplies\b/g, '\\Rightarrow'],
    [/\\Colon\b/g, '::'],
    [/\\(?:var)?o?int(?:ctr)?clockwise\b/g, '\\oint'],
];

/**
 * Macht die Ausgabe von MathLive (`getValue('latex-expanded')`) KaTeX-tauglich:
 * leere Platzhalter einer unfertigen Formel raus, Restbefehle ersetzen.
 */
export function bereinigeLatex(latex) {
    let t = String(latex ?? '').replace(/\\placeholder(?:\[[^\]]*\])?\{\}/g, '');
    for (const [muster, neu] of ERSATZ) t = t.replace(muster, neu);
    return t.trim();
}
