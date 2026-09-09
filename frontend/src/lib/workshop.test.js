import { describe, it, expect } from 'vitest';
import { deriveDocTitle, nurTextHinweis } from './workshop.js'

describe('deriveDocTitle', () => {
    it('nimmt die erste Überschrift', () => {
        expect(deriveDocTitle('Intro\n\n# Arbeitsblatt Bruchrechnung\n\nText')).toBe('Arbeitsblatt Bruchrechnung');
        expect(deriveDocTitle('## Aufgabe 1')).toBe('Aufgabe 1');
    });

    it('fällt auf die erste nicht-leere Zeile zurück (ohne Listen-Markup)', () => {
        expect(deriveDocTitle('- Erster Punkt\n- Zweiter')).toBe('Erster Punkt');
        expect(deriveDocTitle('Einfach Text')).toBe('Einfach Text');
    });

    it('liefert Default bei leer', () => {
        expect(deriveDocTitle('')).toBe('Arbeitsblatt');
        expect(deriveDocTitle('   \n  \n')).toBe('Arbeitsblatt');
        expect(deriveDocTitle(null)).toBe('Arbeitsblatt');
    });

    it('kürzt auf 80 Zeichen', () => {
        const long = '# ' + 'a'.repeat(200);
        expect(deriveDocTitle(long).length).toBe(80);
    });
});

describe("nurTextHinweis", () => {
    it("warnt, wenn ein Bild zurückbliebe", () => {
        expect(nurTextHinweis({ content: "Hier ist dein Bild:", images: [{ image_id: "x" }] }))
            .toContain("nur den Text");
    });

    it("verweist auf den Weg, das Bild zu behalten", () => {
        // Ohne den Verweis wüsste niemand, was stattdessen zu tun ist.
        expect(nurTextHinweis({ images: [{ image_id: "x" }] })).toContain("Knopf am Bild");
    });

    it("schweigt bei einer reinen Textantwort", () => {
        // Dort gibt es nichts zu verlieren — ein Hinweis wäre nur Rauschen.
        expect(nurTextHinweis({ content: "Ein langer Text" })).toBeNull();
        expect(nurTextHinweis({ content: "x", images: [] })).toBeNull();
    });

    it("verträgt eine fehlende Nachricht", () => {
        expect(nurTextHinweis(null)).toBeNull();
        expect(nurTextHinweis(undefined)).toBeNull();
    });
});
