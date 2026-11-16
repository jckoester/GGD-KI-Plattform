import { describe, expect, it } from "vitest";
import { rahmenAngegeben, rahmenMit, stufen, verplanbar, wochenstundenText } from "./curriculum_rahmen.js";

describe("Rahmenangaben (0.46)", () => {
    it("liest die Stufen eines Bands", () => {
        expect(stufen("7/8")).toEqual([7, 8]);
        expect(stufen("8-10")).toEqual([8, 9, 10]);
        expect(stufen("9")).toEqual([9]);
        expect(stufen("")).toEqual([]);
    });

    it("rechnet 30 Stunden je Wochenstunde, erst wenn jede Stufe eine Angabe hat", () => {
        expect(verplanbar({ wochenstunden: { 7: 2, 8: "2" } }, "7/8")).toBe(120);
        expect(verplanbar({ wochenstunden: { 9: "2,5" } }, "9")).toBe(75);
        expect(verplanbar({ wochenstunden: { 7: 2 } }, "7/8")).toBeNull();
        expect(verplanbar({}, "")).toBeNull();
    });

    it("erkennt, ob etwas angegeben ist", () => {
        expect(rahmenAngegeben({})).toBe(false);
        expect(rahmenAngegeben({ lehrwerk: "  " })).toBe(false);
        expect(rahmenAngegeben({ wochenstunden: { 7: 0 } })).toBe(true);
        expect(rahmenAngegeben({ absprachen: "x" })).toBe(true);
    });

    it("zeigt die Wochenstunden des Bands zuerst", () => {
        expect(wochenstundenText({ wochenstunden: { 6: 1, 7: 2, 8: 1.5 } }, "7/8")).toBe("Kl. 7: 2 · Kl. 8: 1,5 · Kl. 6: 1");
    });

    it("ändert eine Kopie und lässt leere Wochenstunden weg", () => {
        const alt = { wochenstunden: { 7: 2 }, lehrwerk: "A" };
        expect(rahmenMit(alt, "wochenstunden", "3", 8)).toEqual({ wochenstunden: { 7: 2, 8: "3" }, lehrwerk: "A" });
        expect(rahmenMit(alt, "wochenstunden", "", 7)).toEqual({ wochenstunden: {}, lehrwerk: "A" });
        expect(rahmenMit(alt, "lehrwerk", "B").lehrwerk).toBe("B");
        expect(alt).toEqual({ wochenstunden: { 7: 2 }, lehrwerk: "A" });
    });
});
