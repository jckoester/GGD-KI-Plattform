// @vitest-environment jsdom
// Der Download baut ein `<a download>` und klickt es — das braucht ein Dokument.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { exportiereFachbegriffe, knotenAlsMarkdown, ApiError } from './api.js'

function antwort(status, { body = null, disposition = null } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (name === 'content-disposition' ? disposition : null) },
    blob: async () => new Blob(['inhalt']),
    json: async () => body ?? {},
  }
}

let geklickt

beforeEach(() => {
  geklickt = []
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
    geklickt.push(this.download)
  })
})

afterEach(() => vi.restoreAllMocks())

describe('exportiereFachbegriffe', () => {
  it('holt das Zip des gewählten Fachs', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      antwort(200, { disposition: 'attachment; filename="fachbegriffe_chemie_2026-09-27.zip"' }),
    )
    await exportiereFachbegriffe('chemie')
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/context/fachbegriffe/export?fach=chemie')
    expect(opts.credentials).toBe('include')
  })

  it('nimmt den Dateinamen des Servers', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      antwort(200, { disposition: 'attachment; filename="fachbegriffe_chemie_2026-09-27.zip"' }),
    )
    await exportiereFachbegriffe('chemie')
    expect(geklickt).toEqual(['fachbegriffe_chemie_2026-09-27.zip'])
  })

  it('hat einen Rückfall, wenn der Kopf fehlt', async () => {
    global.fetch = vi.fn().mockResolvedValue(antwort(200))
    await exportiereFachbegriffe('chemie')
    expect(geklickt).toEqual(['fachbegriffe-chemie.zip'])
  })

  it('meldet fehlende Rechte als ApiError', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      antwort(403, { body: { detail: 'Nur die Fachschaft Chemie kann dort …' } }),
    )
    await expect(exportiereFachbegriffe('chemie')).rejects.toBeInstanceOf(ApiError)
    expect(geklickt).toEqual([])
  })
})

describe('knotenAlsMarkdown', () => {
  it('nimmt den Dateinamen des Servers, nicht die ID', async () => {
    // ⚠️ Der Name ist nicht Kosmetik: Er ist die Herkunftsdatei, über die ein späterer
    // Import den Knoten wiederfindet, solange keine `id` in der Datei steht. Aus
    // „Oxidation (Sauerstoffaufnahme).md" eine „<uuid>.md" zu machen, hieße beim
    // nächsten Lauf einen zweiten Knoten.
    global.fetch = vi.fn().mockResolvedValue(
      antwort(200, { disposition: 'attachment; filename="Oxidation (Sauerstoffaufnahme).md"' }),
    )
    await knotenAlsMarkdown('abc-123')
    expect(global.fetch.mock.calls[0][0]).toBe('/api/context/nodes/abc-123/markdown')
    expect(geklickt).toEqual(['Oxidation (Sauerstoffaufnahme).md'])
  })

  it('fällt auf die ID zurück, wenn der Kopf fehlt', async () => {
    global.fetch = vi.fn().mockResolvedValue(antwort(200))
    await knotenAlsMarkdown('abc-123')
    expect(geklickt).toEqual(['abc-123.md'])
  })

  it('lädt bei 404 nichts herunter', async () => {
    global.fetch = vi.fn().mockResolvedValue(
      antwort(404, { body: { detail: 'Kein Fachbegriff oder Stoffsteckbrief.' } }),
    )
    await expect(knotenAlsMarkdown('abc-123')).rejects.toMatchObject({ status: 404 })
    expect(geklickt).toEqual([])
  })
})
