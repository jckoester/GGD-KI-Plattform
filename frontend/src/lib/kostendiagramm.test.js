import { describe, it, expect } from "vitest";
import { betrag, tabellenZeilen } from "./kostendiagramm.js";

describe("kostendiagramm", () => {
    it("schreibt deutsch — Komma statt Punkt", () => {
        expect(betrag(12.5)).toBe("12,50 €");
        expect(betrag(1234.5)).toBe("1.234,50 €");
    });

    it('zeigt unter einem Euro bis zu vier Stellen — kein „0,00 €" für einen Tag', () => {
        expect(betrag(0.0123)).toBe("0,0123 €");
        expect(betrag(0.5)).toBe("0,50 €");
    });

    it("kennt Dollar für die zweite Spalte", () => {
        expect(betrag(0.0144, "$")).toBe("0,0144 $");
    });

    it("zeigt für Unbekanntes einen Strich", () => {
        expect(betrag(null)).toBe("—");
    });

    it("liefert die Tabellenzeilen", () => {
        expect(tabellenZeilen([{ period: "2026-09", eur: 0.61, usd: 0.714 }])).toEqual([
            { periode: "2026-09", eur: "0,61 €", usd: "0,714 $" },
        ]);
    });
});
