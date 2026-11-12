import { describe, it, expect } from 'vitest';
import {
    kindLabel, mimeExt, codeExt, formatBytes, usagePercent, isSvg, isImageLike, slugify,
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
