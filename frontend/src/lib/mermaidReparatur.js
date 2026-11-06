/**
 * Häufigsten Fehler in Mermaid-Quellen der Modelle beheben, bevor gerendert wird (0.36).
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
