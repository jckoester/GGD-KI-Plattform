import { describe, it, expect } from "vitest";
import { anteilKurz, standText } from "./eigene_bewertung.js";

const GENUG = { zu_wenige: false, plus: 8, minus: 3, anteil: 73 };
const WENIG = { zu_wenige: true, plus: null, minus: null, anteil: null };

describe("standText", () => {
    it("liest einen Stand über der Schwelle", () => {
        expect(standText(GENUG)).toBe("8 hilfreich, 3 nicht hilfreich — 73 % hilfreich");
    });
    it("unter der Schwelle ohne Zahl", () => {
        expect(standText(WENIG, 10)).toBe("noch weniger als 10 Bewertungen");
        expect(standText(undefined)).toMatch(/weniger als/);
    });
});

describe("anteilKurz", () => {
    it("bevorzugt die Schüler:innen", () => {
        expect(anteilKurz({ schueler: GENUG, lehrkraefte: { ...GENUG, anteil: 50 } }).text).toBe("73 %");
    });
    it("nimmt die Lehrkräfte, wenn nur sie genug haben", () => {
        const kurz = anteilKurz({ schueler: WENIG, lehrkraefte: { ...GENUG, anteil: 90 } });
        expect(kurz.text).toBe("90 %");
        expect(kurz.titel).toMatch(/^Lehrkräfte/);
    });
    it("Strich, solange keine Rolle genug hat", () => {
        expect(anteilKurz({ schueler: WENIG, lehrkraefte: WENIG }).text).toBe("—");
        expect(anteilKurz(null).text).toBe("—");
    });
});
