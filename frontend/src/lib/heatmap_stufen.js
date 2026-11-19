/**
 * Stufen der Heatmap unter `statistics/prompts` (0.49, H7).
 *
 * Bis 0.48 grün (Statusfarbe) und die Menge über Deckkraft — die wahrgenommene Farbe hing
 * damit vom Hintergrund ab, und die Werte standen nur im `title`. Jetzt: fünf feste Stufen
 * einer blauen Reihe (Rollen `--diagramm-stufe-1…5` in `layout.css`, hell und dunkel
 * getrennt gewählt und mit `validate_palette.js --ordinal` geprüft), Werte als `aria-label`.
 */

export const STUFEN = 5;

/** Stufe 1…5 einer Zelle, 0 für keine Nachricht. Gleich breite Bereiche bis zum Höchstwert. */
export function stufe(anzahl, hoechstwert) {
    if (!anzahl || anzahl <= 0 || !hoechstwert || hoechstwert <= 0) return 0;
    return Math.min(STUFEN, Math.max(1, Math.ceil((anzahl / hoechstwert) * STUFEN)));
}

/**
 * Bereiche der Stufen für die Legende: `[{ stufe, von, bis }]`, nur Stufen, die bei ganzen
 * Zahlen überhaupt vorkommen können (bei kleinem Höchstwert fallen welche weg).
 */
export function stufenBereiche(hoechstwert) {
    const bereiche = [];
    if (!hoechstwert || hoechstwert <= 0) return bereiche;
    let von = 1;
    for (let k = 1; k <= STUFEN; k++) {
        const bis = Math.floor((hoechstwert * k) / STUFEN);
        if (bis >= von) {
            bereiche.push({ stufe: k, von, bis });
            von = bis + 1;
        }
    }
    return bereiche;
}

/** „Mo, 9–10 Uhr: 14 Nachrichten“ — Beschriftung einer Zelle für Bildschirmleser und Tooltip. */
export function zellenText(tag, stunde, anzahl) {
    const menge = `${anzahl} Nachricht${anzahl === 1 ? "" : "en"}`;
    return `${tag}, ${stunde}–${stunde + 1} Uhr: ${menge}`;
}

/** „1–3“ oder „4“ für die Legende. */
export function bereichText({ von, bis }) {
    return von === bis ? `${von}` : `${von}–${bis}`;
}
