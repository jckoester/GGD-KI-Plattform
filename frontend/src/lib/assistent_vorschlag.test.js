import { describe, it, expect } from "vitest";
import { beschriftung, einleitung, sichtbar, wahl } from "./assistent_vorschlag.js";

const U = (c, mehr = {}) => ({ role: "user", content: c, ...mehr });
const A = (c, mehr = {}) => ({ role: "assistant", content: c, ...mehr });
const OPT = [{ assistant_id: 16, name: "stöchiometrische Berechnungen", text: "…", art: "specific" }];

describe("beschriftung und einleitung", () => {
  it("nennt den Assistenten im Namensschema bzw. das Beenden", () => {
    expect(beschriftung(OPT[0])).toBe("Assistent für stöchiometrische Berechnungen");
    expect(beschriftung({ art: "beenden" })).toBe("Assistent beenden und weiter chatten");
  });
  it("Beenden allein: geht um die Frage", () => {
    expect(einleitung([{ art: "beenden" }])).toMatch(/gehört nicht/);
    expect(einleitung(OPT)).toMatch(/Aufgabe/);
  });
});

describe("sichtbar", () => {
  it("nur an der letzten Antwort und nicht während eines Stroms", () => {
    const msgs = [U("a"), A("1", { vorschlag: OPT })];
    expect(sichtbar(msgs, 1, false)).toBe(true);
    expect(sichtbar(msgs, 1, true)).toBe(false);
    expect(sichtbar([...msgs, U("b"), A("2")], 1, false)).toBe(false);   // verfallen
    expect(sichtbar([U("a"), A("1")], 1, false)).toBe(false);
  });
});

describe("wahl", () => {
  it("Assistent aus der Liste, letzte Nachricht neu beantworten", () => {
    const w = wahl(OPT[0], [U("frage"), A("x")], [{ id: 16, name: "stöchiometrische Berechnungen", icon: "i" }]);
    expect(w).toMatchObject({ beenden: false, neuBeantworten: true, index: 0, text: "frage" });
    expect(w.assistent.icon).toBe("i");
  });
  it("unbekannt in der Liste: Kennung und Name aus dem Vorschlag", () => {
    expect(wahl(OPT[0], [U("f"), A("x")], []).assistent).toEqual({ id: 16, name: "stöchiometrische Berechnungen" });
  });
  it("Beenden; mit Anhängen nicht neu beantworten", () => {
    const w = wahl({ art: "beenden" }, [U("f", { uploadedAttachments: [{}] }), A("x")]);
    expect(w).toMatchObject({ beenden: true, assistent: null, neuBeantworten: false });
  });
});
