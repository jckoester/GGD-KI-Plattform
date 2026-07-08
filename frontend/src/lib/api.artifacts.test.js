import { afterEach, describe, expect, it, vi } from 'vitest';
import { saveImageToLibrary, saveDiagramToLibrary, ApiError } from './api.js';

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
        });
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
