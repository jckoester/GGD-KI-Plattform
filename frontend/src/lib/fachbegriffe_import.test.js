import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  IMPORTIERBARE_TYPEN,
  ZUSTAENDE,
  brauchtEinbettung,
  eingespielt,
  entwuerfe,
  gruppiert,
  lohntSich,
  zusammenfassung,
} from './fachbegriffe_import.js'
import { importiereFachbegriffe, ApiError } from './api.js'

function zeile(datei, zustand, extra = {}) {
  return { datei, titel: datei, zustand, node_id: null, pruefstatus: '', entwurf: false, ...extra }
}

function bericht(extra = {}) {
  return {
    probelauf: true, fach: 'Chemie',
    neu: 0, aktualisiert: 0, unveraendert: 0, uebersprungen: [],
    kanten: 0, kanten_geaendert: 0, neu_einzubetten: 0,
    warnungen: [], dateien: [], vergebene_ids: {},
    offene_ziele: [], offene_fundstellen: [], archivierte_ziele: [],
    ...extra,
  }
}

describe('Reihenfolge der Gruppen', () => {
  it('stellt Handänderungen an den Anfang', () => {
    // ⚠️ Sie sind das Einzige, wozu die Vorschau eine Frage stellt. Hinter dreißig
    // „unverändert"-Zeilen würde die Frage überlesen — und der nächste Lauf
    // überschriebe entweder zu viel oder ließe eine Überarbeitung liegen.
    expect(ZUSTAENDE[0].zustand).toBe('uebersprungen')
  })

  it('lässt leere Gruppen weg', () => {
    const b = bericht({ dateien: [zeile('A', 'neu')] })
    expect(gruppiert(b).map((g) => g.zustand)).toEqual(['neu'])
  })

  it('sortiert nach der festen Reihenfolge, nicht nach dem Bericht', () => {
    const b = bericht({
      dateien: [zeile('A', 'unveraendert'), zeile('B', 'uebersprungen'), zeile('C', 'neu')],
    })
    expect(gruppiert(b).map((g) => g.zustand)).toEqual(['uebersprungen', 'neu', 'unveraendert'])
  })

  it('kommt mit einem leeren Bericht zurecht', () => {
    expect(gruppiert(null)).toEqual([])
    expect(zusammenfassung(null)).toBe('')
  })
})

describe('zusammenfassung', () => {
  it('nennt nur, was vorkommt', () => {
    const b = bericht({ neu: 2, unveraendert: 33 })
    expect(zusammenfassung(b)).toBe('2 neu · 33 unverändert')
  })

  it('sagt es, wenn nichts zu tun ist', () => {
    expect(zusammenfassung(bericht())).toBe('Nichts zu tun.')
  })

  it('zählt Handänderungen als „behalten"', () => {
    expect(zusammenfassung(bericht({ uebersprungen: ['A'] }))).toBe('1 behalten')
  })
})

describe('lohntSich', () => {
  it('ist falsch, wenn ein Lauf nichts täte', () => {
    expect(lohntSich(bericht({ unveraendert: 5 }))).toBe(false)
  })

  it('wird wahr, sobald eine Handänderung angehakt ist', () => {
    // ⚠️ Der Probelauf meldet für einen behaltenen Knoten „0 aktualisiert". Ohne die
    // Auswahl mitzurechnen, wäre der Knopf genau dann aus, wenn er gebraucht wird.
    const b = bericht({ unveraendert: 5, uebersprungen: ['A'] })
    expect(lohntSich(b, [])).toBe(false)
    expect(lohntSich(b, ['A'])).toBe(true)
  })
})

describe('Prüfstatus', () => {
  it('sammelt, was nicht als geprüft markiert ist', () => {
    const b = bericht({
      dateien: [
        zeile('A', 'neu', { entwurf: true, pruefstatus: 'entwurf' }),
        zeile('B', 'neu'),
      ],
    })
    expect(entwuerfe(b).map((z) => z.datei)).toEqual(['A'])
  })
})

describe('nach dem Lauf', () => {
  it('verlinkt nur, was wirklich geschrieben wurde', () => {
    const b = bericht({
      dateien: [
        zeile('A', 'neu', { node_id: 'n1' }),
        zeile('B', 'unveraendert', { node_id: 'n2' }),
        zeile('C', 'uebergangen'),
      ],
    })
    expect(eingespielt(b).map((z) => z.datei)).toEqual(['A'])
  })

  it('weist auf die nächtliche Einbettung hin, wenn Neues dabei war', () => {
    // Über Namen sofort auffindbar, über die Bedeutung erst nachts — wer das nicht
    // liest, sucht direkt danach im Chat und findet nichts.
    expect(brauchtEinbettung(bericht({ neu: 1 }))).toBe(true)
    expect(brauchtEinbettung(bericht({ neu_einzubetten: 3 }))).toBe(true)
    expect(brauchtEinbettung(bericht({ unveraendert: 9 }))).toBe(false)
  })
})

describe('importiereFachbegriffe', () => {
  afterEach(() => vi.restoreAllMocks())

  function mockFetch(status, body) {
    return vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300, status, json: async () => body,
    })
  }

  function datei(name, inhalt = 'x') {
    return new File([inhalt], name, { type: 'text/markdown' })
  }

  it('schickt Probelauf als Vorgabe', async () => {
    global.fetch = mockFetch(200, bericht())
    await importiereFachbegriffe('chemie', [datei('A.md')])
    const [url] = global.fetch.mock.calls[0]
    expect(url).toContain('probelauf=true')
    expect(url).toContain('fach=chemie')
  })

  it('hängt jede Überschreib-Wahl einzeln an', async () => {
    global.fetch = mockFetch(200, bericht())
    await importiereFachbegriffe('chemie', [datei('A.md')], {
      probelauf: false, ueberschreiben: ['Alpha', 'Beta'],
    })
    const [url] = global.fetch.mock.calls[0]
    expect(url).toContain('probelauf=false')
    expect(url).toContain('ueberschreiben=Alpha')
    expect(url).toContain('ueberschreiben=Beta')
  })

  it('schickt die Dateien unter dem Feldnamen `dateien`', async () => {
    global.fetch = mockFetch(200, bericht())
    await importiereFachbegriffe('chemie', [datei('A.md'), datei('B.svg')])
    const [, opts] = global.fetch.mock.calls[0]
    expect(opts.body.getAll('dateien')).toHaveLength(2)
    expect(opts.credentials).toBe('include')
    // ⚠️ Kein `Content-Type` von Hand: Den setzt der Browser samt `boundary`. Eigenhändig
    // gesetzt fehlte die Grenzmarke, und der Server fände keine einzige Datei.
    expect(opts.headers).toBeUndefined()
  })

  it('reicht den Grund einer abgelehnten Datei durch', async () => {
    global.fetch = mockFetch(413, { detail: 'bombe.zip: entpackt 25 MB — höchstens 20 MB.' })
    await expect(importiereFachbegriffe('chemie', [datei('bombe.zip')])).rejects.toMatchObject({
      status: 413,
    })
    await expect(
      importiereFachbegriffe('chemie', [datei('bombe.zip')]),
    ).rejects.toBeInstanceOf(ApiError)
  })
})

describe('welche Sammlungen einen Import anbieten', () => {
  it('sind genau die Typen, die der Leser annimmt', () => {
    // ⚠️ Dieselbe Liste steht als `TYPEN` im Backend. Der Abgleich läuft dort
    // (`test_taxonomy_check.py`) — hier steht sie nur einmal, damit es nicht drei sind.
    expect(IMPORTIERBARE_TYPEN).toEqual(['begriff', 'stoffsteckbrief'])
  })
})
