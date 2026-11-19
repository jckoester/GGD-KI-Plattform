/** Heatmap `statistics/prompts` (0.49, H7). */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { STUFEN, bereichText, stufe, stufenBereiche, zellenText } from "./heatmap_stufen.js";

const SRC = dirname(dirname(fileURLToPath(import.meta.url)));
const lies = (...teile) => readFileSync(join(SRC, ...teile), "utf8");

describe("stufe", () => {
    it("0 ohne Nachricht, sonst 1…5 bis zum Höchstwert", () => {
        expect(stufe(0, 10)).toBe(0);
        expect(stufe(1, 10)).toBe(1);
        expect(stufe(2, 10)).toBe(1);
        expect(stufe(3, 10)).toBe(2);
        expect(stufe(10, 10)).toBe(STUFEN);
        expect(stufe(5, 0)).toBe(0);
    });
});

describe("stufenBereiche", () => {
    it("teilt den Höchstwert in fünf lückenlose Bereiche", () => {
        expect(stufenBereiche(10)).toEqual([
            { stufe: 1, von: 1, bis: 2 }, { stufe: 2, von: 3, bis: 4 }, { stufe: 3, von: 5, bis: 6 },
            { stufe: 4, von: 7, bis: 8 }, { stufe: 5, von: 9, bis: 10 },
        ]);
    });

    it("lässt Stufen weg, die bei kleinem Höchstwert nicht vorkommen — passend zu `stufe`", () => {
        for (const max of [1, 2, 3, 7, 23]) {
            const bereiche = stufenBereiche(max);
            for (let n = 1; n <= max; n++) {
                const b = bereiche.find((x) => n >= x.von && n <= x.bis);
                expect(b?.stufe).toBe(stufe(n, max));
            }
        }
        expect(stufenBereiche(0)).toEqual([]);
    });
});

describe("Texte", () => {
    it("Zelle und Legende", () => {
        expect(zellenText("Mo", 9, 14)).toBe("Mo, 9–10 Uhr: 14 Nachrichten");
        expect(zellenText("So", 23, 1)).toBe("So, 23–24 Uhr: 1 Nachricht");
        expect(bereichText({ von: 1, bis: 3 })).toBe("1–3");
        expect(bereichText({ von: 4, bis: 4 })).toBe("4");
    });
});

describe("Seite und Farben", () => {
    const SEITE = lies("routes", "(admin)", "statistics", "prompts", "+page.svelte");
    const CSS = lies("routes", "layout.css");

    it("keine Deckkraft, kein Grün mehr", () => {
        expect(SEITE).not.toMatch(/opacity:/);
        expect(SEITE).not.toMatch(/-gr-2/);
    });

    it("Zellen tragen ihren Wert für Bildschirmleser, Kopfzellen mit scope", () => {
        expect(SEITE).toContain('<span class="sr-only">{zellenText(');
        expect(SEITE).toMatch(/<th\s+scope="col"/);
        expect(SEITE).toMatch(/<th\s+scope="row"\s+rowspan="3"/);
    });

    it("zentriert, Wochennavigation direkt über der Tabelle, Linien hell zart (Jan 19.11.2026)", () => {
        const block = SEITE.slice(SEITE.indexOf('<div class="flex flex-col items-center gap-3">'));
        expect(block.indexOf('title="Vorherige Woche"')).toBeGreaterThan(-1);
        expect(block.indexOf('title="Vorherige Woche"')).toBeLessThan(block.indexOf("<table"));
        const tabelle = SEITE.slice(SEITE.indexOf("<table"), SEITE.indexOf("</table>"));
        expect(tabelle).not.toContain("border-light-tx-2");
        expect(tabelle).toContain("border-light-ui-3");
    });

    it("fünf Stufen als Rollen, hell und dunkel", () => {
        for (let k = 1; k <= STUFEN; k++) {
            const treffer = CSS.match(new RegExp(`--diagramm-stufe-${k}:`, "g")) ?? [];
            expect(treffer).toHaveLength(2);
        }
    });
});
