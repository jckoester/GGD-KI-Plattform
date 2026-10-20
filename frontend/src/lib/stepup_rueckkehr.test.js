import { describe, expect, it } from "vitest";
import {
  holeFormular,
  lokalesZiel,
  merkeFormular,
  ohneStepupFehler,
  stepupFehlerAusUrl,
  stepupFehlerText,
} from "./stepup_rueckkehr.js";

function speicher() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    size: () => m.size,
  };
}

describe("stepupFehlerText", () => {
  const jetzt = new Date(2026, 9, 19, 14, 7);

  it("nennt bei nicht bestätigter Anmeldung die Uhrzeit fürs Protokoll", () => {
    const text = stepupFehlerText("nicht_frisch", jetzt);
    expect(text).toContain("nicht bestätigen");
    expect(text).toContain("14:07");
  });

  it("unterscheidet Abbruch und anderes Konto", () => {
    expect(stepupFehlerText("abgebrochen", jetzt)).toContain("abgebrochen");
    expect(stepupFehlerText("anderes_konto", jetzt)).toContain("anderen Konto");
    expect(stepupFehlerText("ohne_2fa", jetzt)).toContain("zweiten Faktor");
  });

  it("fällt bei unbekanntem Code auf „fehlgeschlagen“ zurück", () => {
    expect(stepupFehlerText("quatsch", jetzt)).toContain("fehlgeschlagen");
    expect(stepupFehlerText(null)).toBeNull();
  });
});

describe("Adresse", () => {
  it("liest den Code und räumt ihn weg, ohne andere Parameter zu verlieren", () => {
    expect(stepupFehlerAusUrl("?x=1&stepup_fehler=nicht_frisch")).toBe("nicht_frisch");
    expect(stepupFehlerAusUrl("?x=1")).toBeNull();
    expect(ohneStepupFehler("/review", "?x=1&stepup_fehler=abgebrochen")).toBe("/review?x=1");
    expect(ohneStepupFehler("/profile", "?stepup_fehler=abgebrochen")).toBe("/profile");
  });
});

describe("lokalesZiel", () => {
  it("lässt nur Pfade der Plattform durch", () => {
    expect(lokalesZiel("/profile")).toBe("/profile");
    expect(lokalesZiel("/profile?x=1")).toBe("/profile?x=1");
    for (const fremd of ["https://evil.example", "//evil.example", "/\\evil.example", "profile", "", null, "/a\nb"]) {
      expect(lokalesZiel(fremd)).toBeNull();
    }
  });
});

describe("gemerktes Formular", () => {
  it("kommt genau einmal zurück", () => {
    const s = speicher();
    merkeFormular(s, "zugangstoken", { name: "Obsidian", scopes: ["planung"] }, 1000);
    expect(holeFormular(s, "zugangstoken", 2000)).toEqual({ name: "Obsidian", scopes: ["planung"] });
    expect(holeFormular(s, "zugangstoken", 2000)).toBeNull();
  });

  it("verfällt nach einer Viertelstunde und wird trotzdem entfernt", () => {
    const s = speicher();
    merkeFormular(s, "zugangstoken", { name: "alt" }, 0);
    expect(holeFormular(s, "zugangstoken", 16 * 60 * 1000)).toBeNull();
    expect(s.size()).toBe(0);
  });

  it("verträgt kaputte Einträge", () => {
    const s = speicher();
    s.setItem("stepup_formular:zugangstoken", "{kaputt");
    expect(holeFormular(s, "zugangstoken")).toBeNull();
  });
});
