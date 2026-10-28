import { describe, it, expect } from "vitest";
import { anzeige, faecherAlsEintraege, hinzu, naechsterFokus, vorschlaege, weg } from "./chip_auswahl.js";

const FAECHER = faecherAlsEintraege([
  { slug: "geschichte", name: "Geschichte" },
  { slug: "chemie", name: "Chemie", color: "#f00" },
  { slug: "physik", name: "Physik" },
  { slug: "nwt", name: "NwT" },
]);

describe("vorschlaege", () => {
  it("ohne Eingabe alle nicht gewählten", () => {
    expect(vorschlaege(FAECHER, ["physik"], "").map((f) => f.wert)).toEqual(["geschichte", "chemie", "nwt"]);
  });
  it("Wortanfang vor Wortmitte", () => {
    expect(vorschlaege(FAECHER, [], "ch").map((f) => f.wert)).toEqual(["chemie", "geschichte"]);
  });
  it("findet auch über den Wert, ohne Groß/Klein", () => {
    expect(vorschlaege(FAECHER, [], "NWT").map((f) => f.wert)).toEqual(["nwt"]);
  });
  it("Gewähltes wird nicht noch einmal vorgeschlagen", () => {
    expect(vorschlaege(FAECHER, ["chemie"], "chem")).toEqual([]);
  });
  it("Zahlen als Wert (Assistenten-IDs)", () => {
    const a = [{ wert: 18, name: "naturwissenschaftliche Aufgaben" }, { wert: 21, name: "Mathe-Aufgaben" }];
    expect(vorschlaege(a, [18], "").map((e) => e.wert)).toEqual([21]);
    expect(vorschlaege(a, [], "natur").map((e) => e.wert)).toEqual([18]);
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
  it("bekannter Eintrag mit Namen und Farbe", () => {
    expect(anzeige(FAECHER, "chemie")).toEqual({ name: "Chemie", color: "#f00", bekannt: true });
  });
  it("unbekannter Wert bleibt sichtbar", () => {
    expect(anzeige(FAECHER, "nit")).toEqual({ name: "nit", color: null, bekannt: false });
    expect(anzeige([], 42)).toEqual({ name: "42", color: null, bekannt: false });
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
