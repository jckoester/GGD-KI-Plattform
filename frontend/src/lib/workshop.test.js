import { describe, it, expect } from 'vitest';
import { deriveDocTitle } from './workshop.js';

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
