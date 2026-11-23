import { describe, expect, it } from "vitest";
import { anfrageAusUrl, anmeldeZiel, fehlerText } from "./oauth_zustimmung.js";
import { lokalesZiel } from "./stepup_rueckkehr.js";

describe("Zustimmung zu einem KI-Programm", () => {
  it("liest die Anfrage aus der Adresse", () => {
    expect(anfrageAusUrl("?anfrage=abc.def.ghi")).toBe("abc.def.ghi");
    expect(anfrageAusUrl("?anfrage=")).toBeNull();
    expect(anfrageAusUrl("")).toBeNull();
  });

  it("führt zur Anmeldung und zurück auf dieselbe Anfrage", () => {
    const ziel = anmeldeZiel("eyJ.a+b/c=");
    expect(ziel.startsWith("/?return_to=")).toBe(true);
    const zurueck = new URLSearchParams(ziel.slice(1)).get("return_to");
    expect(zurueck).toBe("/oauth/consent?anfrage=eyJ.a%2Bb%2Fc%3D");
    // Die Anmeldeseite nimmt den Rücksprung an (nur lokale Pfade).
    expect(lokalesZiel(zurueck)).toBe(zurueck);
    expect(new URLSearchParams(zurueck.split("?")[1]).get("anfrage")).toBe("eyJ.a+b/c=");
  });

  it("nennt den Grund eines Fehlers", () => {
    expect(fehlerText(403)).toMatch(/Lehrkräfte/);
    expect(fehlerText(404)).toMatch(/nicht eingeschaltet/);
    expect(fehlerText(400, "abgelaufen")).toBe("abgelaufen");
  });
});
