import { describe, it, expect } from 'vitest';
import {
    kindLabel, mimeExt, codeExt, formatBytes, usagePercent, isSvg, isImageLike, slugify,
    werkstattArten, ansichtAusEinstellungen, filterAusAdresse, adresseAusFilter, filterGesetzt,
    nachFachGruppiert,
} from './library.js';

describe('kindLabel', () => {
    it('mappt bekannte Arten auf deutsche Labels', () => {
        expect(kindLabel('image')).toBe('Bild');
        expect(kindLabel('circuit')).toBe('Schaltplan');
        expect(kindLabel('plot')).toBe('Funktionsgraph');
        expect(kindLabel('smiles')).toBe('Strukturformel');
        expect(kindLabel('mermaid')).toBe('Diagramm');
    });
    it('kennt Dokument- und Export-Arten', () => {
        expect(kindLabel('document')).toBe('Dokument');
        expect(kindLabel('export_pdf')).toBe('PDF');
        expect(kindLabel('export_docx')).toBe('Word');
        expect(kindLabel('export_odt')).toBe('ODT');
    });
    it('gibt unbekannte Art unverändert zurück', () => {
        expect(kindLabel('banana')).toBe('banana');
    });
});

describe('mimeExt / codeExt', () => {
    it('mappt MIME auf Dateiendung', () => {
        expect(mimeExt('image/png')).toBe('png');
        expect(mimeExt('image/svg+xml')).toBe('svg');
        expect(mimeExt('application/vnd.geogebra.file')).toBe('ggb');
        expect(mimeExt('text/markdown')).toBe('md');
        expect(mimeExt('application/pdf')).toBe('pdf');
        expect(mimeExt('application/vnd.openxmlformats-officedocument.wordprocessingml.document')).toBe('docx');
        expect(mimeExt('irgendwas')).toBe('bin');
    });
    it('mappt kind auf Code-Endung', () => {
        expect(codeExt('circuit')).toBe('tex');
        expect(codeExt('plot')).toBe('yaml');
        expect(codeExt('smiles')).toBe('smi');
        expect(codeExt('mermaid')).toBe('mmd');
        expect(codeExt('image')).toBe('txt');
        expect(codeExt('unbekannt')).toBe('txt');
    });
});

describe('formatBytes', () => {
    it('formatiert Bytes/KB/MB mit deutschem Komma', () => {
        expect(formatBytes(512)).toBe('512 B');
        expect(formatBytes(2048)).toBe('2,0 KB');
        expect(formatBytes(5 * 1024 * 1024)).toBe('5,0 MB');
        expect(formatBytes(52428800)).toBe('50 MB');
    });
});

describe('usagePercent', () => {
    it('berechnet Prozent und deckelt bei 100', () => {
        expect(usagePercent(0, 100)).toBe(0);
        expect(usagePercent(50, 100)).toBe(50);
        expect(usagePercent(200, 100)).toBe(100);
        expect(usagePercent(10, 0)).toBe(0); // keine Division durch 0
    });
});

describe('isSvg / isImageLike', () => {
    it('erkennt SVG und Bild-MIMEs', () => {
        expect(isSvg('image/svg+xml')).toBe(true);
        expect(isSvg('image/png')).toBe(false);
        expect(isImageLike('image/png')).toBe(true);
        expect(isImageLike('image/svg+xml')).toBe(true);
        expect(isImageLike('application/vnd.geogebra.file')).toBe(false);
    });
});

describe('slugify', () => {
    it('erzeugt sichere Dateinamen-Stämme (inkl. Umlaute)', () => {
        expect(slugify('Mein Schaltplan')).toBe('mein-schaltplan');
        expect(slugify('Übung: f(x)')).toBe('uebung-f-x');
        expect(slugify('')).toBe('produkt');
        expect(slugify('  ---  ')).toBe('produkt');
    });
});

// 0.40: Die Bibliothek heißt „Werkstatt“ und liegt unter /workshop. Alte Adressen leiten um.
import { load as ladeAlteListe } from '../routes/(app)/library/+page.js';
import { load as ladeAltenEditor } from '../routes/(app)/library/[id]/edit/+page.js';
import { load as ladeTools } from '../routes/(app)/tools/+page.js';

function umleitung(fn, arg) {
    try {
        fn(arg);
    } catch (e) {
        return { status: e.status, location: e.location };
    }
    throw new Error('keine Umleitung');
}

describe('alte Adressen (0.40)', () => {
    it('/library → /workshop, Filter bleibt', () => {
        expect(umleitung(ladeAlteListe, { url: new URL('http://x/library?subject_id=3') }))
            .toEqual({ status: 301, location: '/workshop?subject_id=3' });
        expect(umleitung(ladeAlteListe, { url: new URL('http://x/library') }))
            .toEqual({ status: 301, location: '/workshop' });
    });

    it('/library/<id>/edit → /workshop/<id>/edit', () => {
        expect(umleitung(ladeAltenEditor, { params: { id: '42' }, url: new URL('http://x/library/42/edit') }))
            .toEqual({ status: 301, location: '/workshop/42/edit' });
    });

    it('/tools → Werkzeuge in der Assistentenliste', () => {
        expect(umleitung(ladeTools, {})).toEqual({ status: 301, location: '/assistants?erstellt=alle' });
    });
});

describe('Hilfe: alte Seite „Kontextspeicher“ (0.40)', () => {
    it('/help/kontext → /help/bibliothek', async () => {
        const { load } = await import('../routes/(app)/help/[seite]/+page.js');
        let umleitung = null;
        try {
            await load({ params: { seite: 'kontext' }, url: new URL('http://x/help/kontext') });
        } catch (e) {
            umleitung = { status: e.status, location: e.location };
        }
        expect(umleitung).toEqual({ status: 301, location: '/help/bibliothek' });
    });
});


describe('Ordnung der Werkstatt (0.41)', () => {
    it('Arten aus der gemeinsamen Liste, dazu Dateien', () => {
        const produktarten = [
            { id: 'image', filter: 'Bilder' }, { id: 'diagram', filter: 'Diagramme' },
            { id: 'document', filter: 'Dokumente' }, { id: 'lesson_plan', filter: 'Stundenentwürfe' },
        ];
        expect(werkstattArten(produktarten)).toEqual([
            { id: 'image', label: 'Bilder' }, { id: 'diagram', label: 'Diagramme' },
            { id: 'document', label: 'Dokumente' }, { id: 'file', label: 'Dateien' },
        ]);
        // Ohne geladene Liste bleibt wenigstens „Dateien“.
        expect(werkstattArten([])).toEqual([{ id: 'file', label: 'Dateien' }]);
    });

    it('gemerkte Ansicht, Unbekanntes fällt auf die Vorgabe', () => {
        expect(ansichtAusEinstellungen({})).toEqual({ sort: 'updated', gruppiert: false });
        expect(ansichtAusEinstellungen({ werkstatt_ansicht: { sort: 'title', gruppiert: true } }))
            .toEqual({ sort: 'title', gruppiert: true });
        expect(ansichtAusEinstellungen({ werkstatt_ansicht: { sort: 'zufall', gruppiert: 'ja' } }))
            .toEqual({ sort: 'updated', gruppiert: false });
    });

    it('Filter hin und zurück durch die Adresse', () => {
        const f = { q: 'Säure', art: 'diagram', subjectId: 3, topic: 'Redox', baldAblaufend: true, alsBaustein: false };
        const adresse = adresseAusFilter(f);
        expect(filterAusAdresse(new URLSearchParams(adresse.slice(1)))).toEqual(f);
        expect(adresseAusFilter({ q: '', art: null, subjectId: null, topic: null, baldAblaufend: false, alsBaustein: false }))
            .toBe('');
    });

    it('Unbekanntes in der Adresse ist kein Filter', () => {
        const f = filterAusAdresse(new URLSearchParams('art=zeitreise&subject_id=abc&bald=ja'));
        expect(f.art).toBeNull();
        expect(f.subjectId).toBeNull();
        expect(f.baldAblaufend).toBe(false);
        expect(filterGesetzt(f)).toBe(false);
    });

    it('der alte Link von der Fachseite (?subject_id=) wirkt weiter', () => {
        expect(filterAusAdresse(new URLSearchParams('subject_id=7')).subjectId).toBe(7);
    });

    it('nach Fach gruppiert: alphabetisch, ohne Fach zuletzt, Reihenfolge innen bleibt', () => {
        const items = [
            { id: 1, subject_id: 2 }, { id: 2, subject_id: null }, { id: 3, subject_id: 1 }, { id: 4, subject_id: 2 },
        ];
        const faecher = { 1: { name: 'Chemie' }, 2: { name: 'Biologie' } };
        expect(nachFachGruppiert(items, faecher).map((g) => [g.name, g.items.map((i) => i.id)])).toEqual([
            ['Biologie', [1, 4]], ['Chemie', [3]], ['Ohne Fach', [2]],
        ]);
    });
});
