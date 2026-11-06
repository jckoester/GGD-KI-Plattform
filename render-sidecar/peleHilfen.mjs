/**
 * Gemeinsame Helfer für Pele-Diagramme (0.36) — im Frontend **und** im Render-Sidecar.
 *
 * ⚠️ **Zwei Kopien, ein Inhalt.** `render-sidecar/peleHilfen.mjs` ist eine wortgleiche Kopie dieser
 * Datei (der Sidecar ist ein eigenes Paket mit eigenem Docker-Build). `peleHilfen.test.js` prüft,
 * dass beide gleich sind. Deshalb hier keine Importe.
 *
 * ## mermaidReparieren
 *
 * Häufigsten Fehler in Mermaid-Quellen der Modelle beheben, bevor gerendert wird.
 *
 * **Der Fehler.** Klammern in einer Beschriftung ohne Anführungszeichen —
 * `B[Ammonium (NH₄⁺) im Boden]`, `-->|Fixierung (Bakterien)|`. Mermaid liest `(` als Beginn einer
 * Knotenform und bricht ab; gültig wäre `B["Ammonium (NH₄⁺) im Boden"]`. In der Chemie ist das
 * die Regel, nicht die Ausnahme: Von 19 echten Diagrammen aus Chats und Messungen waren 11
 * ungültig, 9 davon genau deshalb (Plaene/Messungen-Pele). Mermaid 11 und Pele scheitern gleich.
 *
 * **Die Reparatur.** Nur in Flussdiagrammen (`graph`/`flowchart`), nur Beschriftungen in `[…]`
 * und `|…|`, nur wenn sie Klammern enthalten und noch nicht in Anführungszeichen stehen. Andere
 * Knotenformen (`[(…)]`, `[/…/]`, `[[…]]`, `["…"]`) und Zeilen mit `style`, `classDef` usw.
 * bleiben unberührt. Im Korpus: 26 → 35 von 38 gültig, kein gültiges Diagramm danach ungültig.
 *
 * Was danach noch scheitert, zeigt wie bisher Meldung und Quelle.
 */

const HEIKEL = /[()[\]{}]/;

function inAnfuehrungszeichen(text) {
    return `"${text.replace(/"/g, '#quot;')}"`;
}

// Kantentext |…|, der nicht schon mit Anführungszeichen beginnt.
const KANTE = /\|(?!")([^|]+)\|/g;
// Knoten ID[…]: keine andere Form ([( [/ [\ [[ ["), Inhalt darf eine Ebene runder Klammern
// enthalten; danach muss etwas folgen, das hinter einem Knoten stehen kann.
const KNOTEN =
    /(\b[\w-]+)\[(?!["[/\\(])((?:[^[\]]|\([^()]*\))*?)\](?=\s*($|-|&|:::|\||;|\s[A-Za-z]))/g;
const UNBERUEHRT = /^\s*(style|classDef|class|click|linkStyle|%%)/;

/** Die Quelle mit Beschriftungen in Anführungszeichen, wo Klammern sie sonst brechen. */
export function mermaidReparieren(quelle) {
    if (!/^\s*(graph|flowchart)\b/.test(quelle)) return quelle;
    return quelle
        .split('\n')
        .map((zeile) => {
            if (UNBERUEHRT.test(zeile)) return zeile;
            return zeile
                .replace(KANTE, (ganz, text) =>
                    HEIKEL.test(text) ? `|${inAnfuehrungszeichen(text)}|` : ganz)
                .replace(KNOTEN, (ganz, id, text) =>
                    HEIKEL.test(text) ? `${id}[${inAnfuehrungszeichen(text)}]` : ganz);
        })
        .join('\n');
}

/**
 * Feste Farben für ein Diagramm, das die Seite verlässt (Datei, Bibliothek, Export) — hell, wie
 * auf Papier. Dieselben Werte wie die hellen Tokens in `hljs-theme.css`, nur mit weißem Grund.
 */
export const DATEI_FARBEN = {
    bg: '#ffffff',
    fg: '#100f0f',
    muted: '#575653',
    line: '#100f0f',
    surface: '#f2f0e5',
    'surface-alt': '#e6e4d9',
    border: '#cecdc3',
    accent: '#205ea6',
};

/**
 * Pele-SVG ohne CSS-Variablen.
 *
 * Pele schreibt Farben über zwei Ebenen: `--_fg:var(--pele-fg,#1f1f1f)` im `style` des
 * Wurzelelements, darunter `fill="var(--_fg)"`. Außerhalb der Seite (Word, WeasyPrint, Inkscape)
 * wird `var()` nicht ausgewertet. Erst `--pele-*` durch die Palette ersetzen (sonst den
 * Rückfallwert), dann die internen `--_x`.
 */
export function festeFarben(svg, palette = DATEI_FARBEN) {
    let s = svg.replace(/var\(--pele-([a-z0-9-]+),([^()]*)\)/g, (_, name, rueckfall) =>
        palette[name] ?? rueckfall);
    const intern = Object.fromEntries(
        [...s.matchAll(/--(_[a-z0-9]+):([^;"]+)/g)].map((m) => [m[1], m[2]]));
    for (let i = 0; i < 3; i++) {
        s = s.replace(/var\(--(_[a-z0-9]+)\)/g, (ganz, name) => intern[name] ?? ganz);
    }
    return s.replace(/--_[a-z0-9]+:[^;"]+;?/g, '');
}
