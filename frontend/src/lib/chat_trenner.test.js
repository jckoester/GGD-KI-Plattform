/** Trenner bei Modellwechsel: nur für die eigene Wahl, nicht für die Aufgaben-Weiterleitung (7a). */
import { describe, it, expect } from "vitest";
import { gewaehltesModell, modellGewechselt, weitergeleitetAus } from "./chat_trenner.js";

const standard = { role: "assistant", model: "chat-standard" };
const weitergeleitet = { role: "assistant", model: "chat-komplex", weitergeleitetVon: "chat-standard" };
const gewaehltKomplex = { role: "assistant", model: "chat-komplex" };

describe("modellGewechselt", () => {
    it("Weiterleitung hin und zurück: kein Trenner", () => {
        expect(modellGewechselt(standard, weitergeleitet)).toBe(false);
        expect(modellGewechselt(weitergeleitet, standard)).toBe(false);
    });
    it("selbst gewählt: Trenner, auch nach einer weitergeleiteten Antwort", () => {
        expect(modellGewechselt(standard, gewaehltKomplex)).toBe(true);
        expect(modellGewechselt(weitergeleitet, gewaehltKomplex)).toBe(true);
    });
    it("ohne vorige Antwort oder ohne Modell: kein Trenner", () => {
        expect(modellGewechselt(null, standard)).toBe(false);
        expect(modellGewechselt(standard, { role: "assistant", model: null })).toBe(false);
    });
});

describe("gewaehltesModell und weitergeleitetAus", () => {
    it("liest das Ausgangsmodell", () => {
        expect(gewaehltesModell(weitergeleitet)).toBe("chat-standard");
        expect(gewaehltesModell(standard)).toBe("chat-standard");
    });
    it("Kopfzeilen: nur bei abweichender Wahl", () => {
        expect(weitergeleitetAus("chat-komplex", "chat-standard")).toBe("chat-standard");
        expect(weitergeleitetAus("chat-standard", "chat-standard")).toBe(null);
        expect(weitergeleitetAus("chat-standard", null)).toBe(null);
    });
});
