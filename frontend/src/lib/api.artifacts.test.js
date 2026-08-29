import { afterEach, describe, expect, it, vi } from 'vitest';
import { saveImageToLibrary, saveDiagramToLibrary, getPlotGgbBlob, ApiError } from './api.js';

function mockFetch(status, body) {
    return vi.fn().mockResolvedValue({
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
    });
}

afterEach(() => {
    vi.restoreAllMocks();
});

describe('saveImageToLibrary', () => {
    it('POSTet image_id an /artifacts/from-image', async () => {
        global.fetch = mockFetch(200, { id: 'a', created: true });
        const r = await saveImageToLibrary('img-123');
        expect(r.created).toBe(true);
        const [url, opts] = global.fetch.mock.calls[0];
        expect(url).toBe('/api/artifacts/from-image');
        expect(opts.method).toBe('POST');
        expect(opts.credentials).toBe('include');
        expect(JSON.parse(opts.body)).toEqual({ image_id: 'img-123', title: null });
    });

    it('wirft ApiError mit Status bei voller Bibliothek (409)', async () => {
        global.fetch = mockFetch(409, { detail: 'Deine Bibliothek ist voll.' });
        await expect(saveImageToLibrary('img-123')).rejects.toMatchObject({
            status: 409,
            message: 'Deine Bibliothek ist voll.',
        });
    });
});

describe('saveDiagramToLibrary', () => {
    it('sendet kind/source/svg an /artifacts/from-diagram (mermaid)', async () => {
        global.fetch = mockFetch(200, { id: 'a', created: true });
        await saveDiagramToLibrary('mermaid', 'graph TD; A-->B', { svg: '<svg>x</svg>' });
        const [url, opts] = global.fetch.mock.calls[0];
        expect(url).toBe('/api/artifacts/from-diagram');
        expect(JSON.parse(opts.body)).toEqual({
            kind: 'mermaid',
            source: 'graph TD; A-->B',
            svg: '<svg>x</svg>',
            title: null,
            message_id: null,   // ohne Nachrichtenbezug: Herkunft bleibt unbekannt
        });
    });

    it('gibt die Nachrichten-ID mit, damit das Backend die Herkunft nachschlagen kann', async () => {
        global.fetch = mockFetch(200, { id: 'a', created: true });
        await saveDiagramToLibrary('mermaid', 'graph TD; A-->B', {
            svg: '<svg>x</svg>',
            messageId: '11111111-2222-3333-4444-555555555555',
        });
        const [, opts] = global.fetch.mock.calls[0];
        const body = JSON.parse(opts.body);
        expect(body.message_id).toBe('11111111-2222-3333-4444-555555555555');
        // Bewusst NUR die ID — ein vom Browser behaupteter Modellname hätte in einer
        // Quellenangabe keinen Wert.
        expect(body).not.toHaveProperty('provider_model');
    });

    it('lässt svg für server-gerenderte Diagramme weg (null)', async () => {
        global.fetch = mockFetch(200, { id: 'a', created: false });
        await saveDiagramToLibrary('plot', 'functions: []');
        const body = JSON.parse(global.fetch.mock.calls[0][1].body);
        expect(body.kind).toBe('plot');
        expect(body.svg).toBeNull();
    });

    it('wirft ApiError bei 422', async () => {
        global.fetch = mockFetch(422, { detail: 'unbekannter Diagrammtyp' });
        const err = await saveDiagramToLibrary('banana', 'x').catch((e) => e);
        expect(err).toBeInstanceOf(ApiError);
        expect(err.status).toBe(422);
    });
});

describe('getPlotGgbBlob', () => {
    it('POSTet die Plot-Quelle und liefert einen Blob', async () => {
        const blob = new Blob(['PK'], { type: 'application/vnd.geogebra.file' });
        global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => blob });
        const r = await getPlotGgbBlob('functions:\n  - x^2');
        expect(r).toBe(blob);
        const [url, opts] = global.fetch.mock.calls[0];
        expect(url).toBe('/api/artifacts/ggb');
        expect(opts.method).toBe('POST');
        expect(JSON.parse(opts.body)).toEqual({ source: 'functions:\n  - x^2', title: null });
    });

    it('wirft ApiError mit Status bei ungültiger Spec (422)', async () => {
        global.fetch = mockFetch(422, { detail: 'ungültige Plot-Spec' });
        await expect(getPlotGgbBlob('kaputt')).rejects.toMatchObject({ status: 422 });
    });
});
