import { describe, expect, it } from "vitest";
import { mitVorschlag, umgeschaltet } from "./produktarten.js";

const ARTEN = [
    { id: "image", marke: "erstellt Bilder", filter: "Bilder", faehigkeit: "image_generation" },
    { id: "diagram", marke: "erstellt Diagramme", filter: "Diagramme", faehigkeit: null },
    { id: "year_plan", marke: "plant das Schuljahr", filter: "Jahresplanung", faehigkeit: "planning" },
];

describe("umgeschaltet", () => {
    it("ordnet nach der Liste und entfernt Doppelte", () => {
        expect(umgeschaltet(["year_plan"], "image", true, ARTEN)).toEqual(["image", "year_plan"]);
        expect(umgeschaltet(["image"], "image", true, ARTEN)).toEqual(["image"]);
    });

    it("nimmt heraus", () => {
        expect(umgeschaltet(["image", "diagram"], "image", false, ARTEN)).toEqual(["diagram"]);
    });

    it("verträgt fehlende Angabe", () => {
        expect(umgeschaltet(undefined, "diagram", true, ARTEN)).toEqual(["diagram"]);
    });
});

describe("mitVorschlag", () => {
    it("schlägt zur Fähigkeit die Art vor", () => {
        expect(mitVorschlag(["diagram"], "planning", ARTEN)).toEqual(["diagram", "year_plan"]);
    });

    it("lässt alles, wenn die Fähigkeit nichts herstellt", () => {
        expect(mitVorschlag(["diagram"], "lesson_planning", ARTEN)).toEqual(["diagram"]);
        expect(mitVorschlag(["diagram"], "context_search", [])).toEqual(["diagram"]);
    });
});
