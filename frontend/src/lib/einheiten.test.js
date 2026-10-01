import { describe, it, expect } from "vitest";
import { ausUsd, zahl, text, kurshinweis, EINHEITEN_JE_EURO, BEZEICHNUNG } from "./einheiten.js";

describe("einheiten", () => {
    it("rechnet USD über den Kurs in Einheiten", () => {
        // 0,000749 € je Median-Nachricht mit `chat-standard` → rund 7,5 Einheiten.
        expect(ausUsd(0.000877, 1.1705)).toBeCloseTo(7.49, 1);
    });

    it("liefert null, wenn Betrag oder Kurs fehlen", () => {
        expect(ausUsd(null, 1.17)).toBeNull();
        expect(ausUsd(0.001, null)).toBeNull();
        expect(ausUsd(0.001, 0)).toBeNull();
    });

    it("zeigt ganze Zahlen ab einer Einheit", () => {
        expect(zahl(7.5)).toBe("8");
        expect(zahl(239)).toBe("239");
        expect(zahl(1)).toBe("1");
    });

    it("zeigt unter einer Einheit eine Nachkommastelle", () => {
        expect(zahl(0.43)).toBe("0,4");
        expect(zahl(0.75)).toBe("0,8");
    });

    it("zeigt nie 0 für einen Betrag größer null", () => {
        // ⚠️ Genau der Fehler, den der Euro gemacht hat — in neuer Einheit wäre er
        // kein bisschen besser.
        expect(zahl(0.004)).toBe("<0,1");
        expect(zahl(0.0000001)).toBe("<0,1");
        expect(zahl(0)).toBe("0");
    });

    it("beugt das Anzeigewort", () => {
        // Gegen die Konstante geprüft, nicht gegen ein Literal: Ein Namenswechsel soll
        // **eine** Zeile sein und nicht zwanzig Testerwartungen umwerfen.
        expect(text(1)).toBe(`1 ${BEZEICHNUNG.singular}`);
        expect(text(8)).toBe(`8 ${BEZEICHNUNG.plural}`);
        expect(text(0.43)).toBe(`0,4 ${BEZEICHNUNG.plural}`);
    });

    it("heißt heute „Einheit“ / „Einheiten“", () => {
        // Der eine Test, der das Wort **festnagelt**. Ein Wechsel ist damit eine
        // bewusste Änderung mit sichtbarem Diff — und nicht etwas, das nebenbei
        // durchrutscht, weil alle anderen Tests mitwandern.
        expect(BEZEICHNUNG).toEqual({ singular: "Einheit", plural: "Einheiten" });
    });

    it("nennt den Kurs in der Oberfläche", () => {
        expect(kurshinweis()).toBe(`10.000 ${BEZEICHNUNG.plural} = 1 €`);
        expect(kurshinweis(1000)).toBe(`1.000 ${BEZEICHNUNG.plural} = 1 €`);
    });

    it("hat 10 000 als Vorgabe", () => {
        expect(EINHEITEN_JE_EURO).toBe(10000);
    });
});
