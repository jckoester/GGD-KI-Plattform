import { describe, it, expect } from "vitest";
import { datumKurz, reihen, zeigbar, euro, tabellenZeilen } from "./budgetverlauf.js";

const verlauf = [
    { montag: "2026-09-14", soll_eur: 10, ist_eur: 1, unterricht: true },
    { montag: "2026-09-21", soll_eur: 20, ist_eur: 2.5, unterricht: true },
    { montag: "2026-09-28", soll_eur: 20, ist_eur: null, unterricht: false },
];

describe("budgetverlauf", () => {
    it("kürzt das Datum auf Tag und Monat", () => {
        expect(datumKurz("2026-09-14")).toBe("14.09.");
    });

    it("liefert beide Reihen und lässt kommende Wochen leer statt null Euro", () => {
        const r = reihen(verlauf);
        expect(r.labels).toEqual(["14.09.", "21.09.", "28.09."]);
        expect(r.soll).toEqual([10, 20, 20]);
        // ⚠️ null, nicht 0 — eine Null sähe aus wie „nichts verbraucht".
        expect(r.ist).toEqual([1, 2.5, null]);
    });

    it("zeigt erst etwas, wenn es eine vergangene Woche gibt", () => {
        expect(zeigbar(verlauf)).toBe(true);
        expect(zeigbar(verlauf.map((p) => ({ ...p, ist_eur: null })))).toBe(false);
        expect(zeigbar([])).toBe(false);
        expect(zeigbar(undefined)).toBe(false);
    });

    it("formatiert Euro und zeigt für Unbekanntes einen Strich", () => {
        expect(euro(2.5)).toMatch(/2,50\s€/);
        expect(euro(null)).toBe("—");
    });

    it("markiert Ferienwochen in der Tabelle", () => {
        expect(tabellenZeilen(verlauf).map((z) => z.ferien)).toEqual([false, false, true]);
        expect(tabellenZeilen(verlauf)[2].ist).toBe("—");
    });
});
