import { describe, it, expect } from "vitest";
import { anzeige, hinzu, naechsterFokus, vorschlaege, weg } from "./fach_mehrfachauswahl.js";

const FAECHER = [
  { slug: "geschichte", name: "Geschichte" },
  { slug: "chemie", name: "Chemie", color: "#f00" },
  { slug: "physik", name: "Physik" },
  { slug: "nwt", name: "NwT" },
];

describe("vorschlaege", () => {
  it("ohne Eingabe alle nicht gewählten", () => {
    expect(vorschlaege(FAECHER, ["physik"], "").map((f) => f.slug)).toEqual(["geschichte", "chemie", "nwt"]);
  });
  it("Wortanfang vor Wortmitte", () => {
    expect(vorschlaege(FAECHER, [], "ch").map((f) => f.slug)).toEqual(["chemie", "geschichte"]);
  });
  it("findet auch über den Slug, ohne Groß/Klein", () => {
    expect(vorschlaege(FAECHER, [], "NWT").map((f) => f.slug)).toEqual(["nwt"]);
  });
  it("Gewähltes wird nicht noch einmal vorgeschlagen", () => {
    expect(vorschlaege(FAECHER, ["chemie"], "chem")).toEqual([]);
  });
});

describe("hinzu und weg", () => {
  it("keine Dublette, Reihenfolge bleibt", () => {
    expect(hinzu(["chemie"], "physik")).toEqual(["chemie", "physik"]);
    expect(hinzu(["chemie"], "chemie")).toEqual(["chemie"]);
    expect(weg(["chemie", "physik"], "chemie")).toEqual(["physik"]);
  });
});

describe("anzeige", () => {
  it("bekanntes Fach mit Namen und Farbe", () => {
    expect(anzeige(FAECHER, "chemie")).toEqual({ name: "Chemie", color: "#f00", bekannt: true });
  });
  it("unbekannter Slug bleibt sichtbar", () => {
    expect(anzeige(FAECHER, "nit")).toEqual({ name: "nit", color: null, bekannt: false });
  });
});

describe("naechsterFokus", () => {
  it("läuft im Kreis und startet sinnvoll", () => {
    expect(naechsterFokus(-1, 3, 1)).toBe(0);
    expect(naechsterFokus(-1, 3, -1)).toBe(2);
    expect(naechsterFokus(2, 3, 1)).toBe(0);
    expect(naechsterFokus(0, 0, 1)).toBe(-1);
  });
});
