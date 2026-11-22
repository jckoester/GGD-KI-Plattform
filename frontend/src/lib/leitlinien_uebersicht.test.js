/** Raster der Leitlinien-Übersicht (0.53, AU). */
import { describe, it, expect } from "vitest";
import { GANZ, fundstelleHref, hoechstwert, spalten, zeilen, zellenText } from "./leitlinien_uebersicht.js";

const fs = (fach_id, extra = {}) => ({ fach_id, curriculum_id: "c", kapitel_id: "k", ...extra });
const U = {
    leitlinie: { node_id: "l", kuerzel: "SDG", titel: "Nachhaltigkeit" },
    faecher: [{ id: 2, name: "Mathe" }, { id: 1, name: "Bio" }],
    alle_faecher: [{ id: 2, name: "Mathe" }, { id: 3, name: "Chemie" }, { id: 1, name: "Bio" }],
    aspekte: [
        { node_id: "a1", kuerzel: "SDG1", titel: "Armut", fundstellen: [fs(1), fs(1), fs(2)] },
        { node_id: "a2", kuerzel: "SDG2", titel: "Hunger", fundstellen: [] },
    ],
    ganz: [],
};

describe("Raster", () => {
    it("Spalten je Aspekt, leere markiert", () => {
        expect(spalten(U).map((s) => [s.kuerzel, s.leer])).toEqual([["SDG1", false], ["SDG2", true]]);
    });

    it("„als Ganzes“ nur mit solchen Verweisen, dann vorn", () => {
        const sp = spalten({ ...U, ganz: [fs(3)] });
        expect(sp[0].schluessel).toBe(GANZ);
        expect(sp[0].titel).toBe("Nachhaltigkeit als Ganzes");
    });

    it("Zeilen nur mit Eintragungen oder alle Fächer, in derselben Reihenfolge", () => {
        expect(zeilen(U).map((z) => [z.name, z.zellen, z.summe])).toEqual([
            ["Mathe", [1, 0], 1], ["Bio", [2, 0], 2]]);
        expect(zeilen(U, true).map((z) => z.name)).toEqual(["Mathe", "Chemie", "Bio"]);
        expect(zeilen(U, true)[1].zellen).toEqual([0, 0]);
    });

    it("Höchstwert, auch ohne Zeilen", () => {
        expect(hoechstwert(zeilen(U))).toBe(2);
        expect(hoechstwert([])).toBe(0);
    });
});

describe("Texte und Wege", () => {
    it("Zellentext", () => {
        expect(zellenText("Bio", "SDG1", 2)).toBe("Bio, SDG1: 2 Fundstellen");
        expect(zellenText("Bio", "SDG1", 1)).toBe("Bio, SDG1: 1 Fundstelle");
        expect(zellenText("Bio", "SDG2", 0)).toBe("Bio, SDG2: keine Fundstellen");
    });

    it("Fundstelle öffnet das Curriculum am Kapitel", () => {
        expect(fundstelleHref(fs(1), "/x/y")).toBe("/knowledge/curriculum/c?back=%2Fx%2Fy#kapitel-k");
    });
});
