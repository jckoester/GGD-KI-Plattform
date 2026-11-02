import { describe, expect, it } from "vitest";
import { datenText, zielText } from "./auditanzeige.js";

describe("datenText", () => {
    it("reiht Schlüssel und Werte", () => {
        expect(datenText({ von: "open", nach: "done", anhang_behalten: false }))
            .toBe("von: open · nach: done · anhang_behalten: nein");
    });
    it("zeigt Listen als Aufzählung und Gebilde als JSON", () => {
        expect(datenText({ teams: ["a", "b"], leer: [], x: { y: { z: 1 } } }))
            .toBe('teams: a, b · leer: — · x: {"y":{"z":1}}');
    });
    it("zeigt eine Ebene Verschachtelung lesbar", () => {
        expect(datenText({ geloescht: { auth: 0, admin: 2 } })).toBe("geloescht: auth 0, admin 2");
    });
    it("bleibt bei leeren Daten leer", () => {
        expect(datenText({})).toBe("");
        expect(datenText(null)).toBe("");
    });
});

describe("zielText", () => {
    it("verbindet Typ und Kennung", () => {
        expect(zielText("assistant", "12")).toBe("assistant 12");
        expect(zielText("site_text", null)).toBe("site_text");
        expect(zielText(null, null)).toBe("");
    });
});
