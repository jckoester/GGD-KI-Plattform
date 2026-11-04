import { describe, it, expect } from "vitest";
import { anteilHoch, anteilText, bewertungCsv, gesamt, zeilenName } from "./bewertungsstatistik.js";

const zeile = { schluessel: "7", name: "Chemie-Tutor", plus_schueler: 8, minus_schueler: 2,
    plus_lehrkraft: 1, minus_lehrkraft: 1 };

describe("anteilHoch", () => {
    it("erst ab der Mindestzahl", () => {
        expect(anteilHoch(8, 1)).toBeNull();
        expect(anteilHoch(8, 2)).toBe(80);
        expect(anteilHoch(0, 0, 0)).toBeNull();
    });
    it("als Text mit Strich darunter", () => {
        expect(anteilText(3, 0)).toBe("—");
        expect(anteilText(9, 3)).toBe("75 %");
    });
});

describe("gesamt", () => {
    it("zählt beide Rollen zusammen", () => {
        expect(gesamt(zeile)).toEqual({ plus: 9, minus: 3 });
    });
});

describe("zeilenName", () => {
    it("benennt leere Schlüssel", () => {
        expect(zeilenName(zeile, "assistent")).toBe("Chemie-Tutor");
        expect(zeilenName({ schluessel: null, name: null }, "assistent")).toBe("Ohne Assistent");
        expect(zeilenName({ schluessel: null, name: null }, "modell")).toBe("Modell unbekannt");
    });
});

describe("bewertungCsv", () => {
    it("schreibt Kopf und Zeilen mit Semikolon", () => {
        const csv = bewertungCsv([zeile], "assistent");
        expect(csv).toContain("assistent;plus_schueler;minus_schueler;plus_lehrkraft;minus_lehrkraft");
        expect(csv).toContain("Chemie-Tutor;8;2;1;1");
    });
});
