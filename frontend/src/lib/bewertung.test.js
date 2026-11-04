import { describe, it, expect } from "vitest";
import { alsAnzeige, naechsteBewertung, zeigeDaumen } from "./bewertung.js";

describe("naechsteBewertung", () => {
    it("setzt, schaltet um und nimmt zurück", () => {
        expect(naechsteBewertung(null, 1)).toBe(1);
        expect(naechsteBewertung(1, -1)).toBe(-1);
        expect(naechsteBewertung(-1, -1)).toBe(0);
    });
});

describe("alsAnzeige", () => {
    it("macht aus 0 und Unbekanntem keine Bewertung", () => {
        expect(alsAnzeige(1)).toBe(1);
        expect(alsAnzeige(-1)).toBe(-1);
        expect(alsAnzeige(0)).toBeNull();
        expect(alsAnzeige(undefined)).toBeNull();
    });
});

describe("zeigeDaumen", () => {
    const antwort = { role: "assistant", id: "a1", content: "Antwort" };

    it("an einer fertigen Antwort im bewertbaren Chat", () => {
        expect(zeigeDaumen({ bewertbar: true, message: antwort, isStreaming: false })).toBe(true);
    });

    it("nicht im Test- oder Vorschau-Chat", () => {
        expect(zeigeDaumen({ bewertbar: false, message: antwort, isStreaming: false })).toBe(false);
    });

    it("nicht beim Streamen, nicht ohne Kennung, nicht leer, nicht an eigenen Fragen", () => {
        expect(zeigeDaumen({ bewertbar: true, message: antwort, isStreaming: true })).toBe(false);
        expect(zeigeDaumen({ bewertbar: true, message: { ...antwort, id: null } })).toBe(false);
        expect(zeigeDaumen({ bewertbar: true, message: { ...antwort, content: "  " } })).toBe(false);
        expect(zeigeDaumen({ bewertbar: true, message: { ...antwort, role: "user" } })).toBe(false);
    });
});
