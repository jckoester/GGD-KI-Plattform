import { describe, it, expect } from 'vitest'
import { scanStructured } from './pii_client.js'

/** Hilfsfunktion: nur die Kategorien der Treffer. */
const cats = (text) => scanStructured(text).map((s) => s.category)

describe('scanStructured — E-Mail', () => {
    it('erkennt eine einfache Adresse', () => {
        const spans = scanStructured('Schreib mir an max.mustermann@example.com bitte.')
        expect(spans).toHaveLength(1)
        expect(spans[0].category).toBe('email')
        expect(spans[0].text).toBe('max.mustermann@example.com')
    })

    it('Span-Grenzen zeigen exakt auf die Adresse', () => {
        const text = 'a@b.de'
        const [s] = scanStructured(text)
        expect(text.slice(s.start, s.end)).toBe('a@b.de')
    })

    it('mehrere Adressen', () => {
        expect(cats('x@y.de und z@w.org')).toEqual(['email', 'email'])
    })

    it('kein @ → keine Adresse', () => {
        expect(scanStructured('Treffen um 8 Uhr im Park')).toEqual([])
    })
})

describe('scanStructured — IBAN', () => {
    it('erkennt eine gruppierte deutsche IBAN', () => {
        const spans = scanStructured('Überweise auf DE89 3704 0044 0532 0130 00 danke')
        expect(spans).toHaveLength(1)
        expect(spans[0].category).toBe('iban')
        expect(spans[0].text).toBe('DE89 3704 0044 0532 0130 00')
    })

    it('erkennt eine zusammenhängende IBAN', () => {
        expect(cats('DE89370400440532013000')).toEqual(['iban'])
    })

    it('eine IBAN wird nicht zusätzlich als Telefon markiert', () => {
        // Die Ziffernblöcke einer IBAN ähneln einer Telefonnummer — Vorrang IBAN.
        const spans = scanStructured('DE89 3704 0044 0532 0130 00')
        expect(spans).toHaveLength(1)
        expect(spans[0].category).toBe('iban')
    })
})

describe('scanStructured — Telefon', () => {
    it.each([
        ['0151 12345678', '0151 12345678'],
        ['+49 151 12345678', '+49 151 12345678'],
        ['030/12345678', '030/12345678'],
        ['0711-1234567', '0711-1234567'],
    ])('erkennt %s', (text, expected) => {
        const spans = scanStructured(text)
        expect(spans).toHaveLength(1)
        expect(spans[0].category).toBe('telefon')
        expect(spans[0].text).toBe(expected)
    })

    it('erkennt eine Nummer mitten im Satz', () => {
        const text = 'Ruf mich an unter 0151 23456789 wenn du Zeit hast'
        const [s] = scanStructured(text)
        expect(s.category).toBe('telefon')
        expect(text.slice(s.start, s.end)).toBe('0151 23456789')
    })
})

describe('scanStructured — False-Positive-Disziplin (Telefon)', () => {
    it.each([
        'Das war am 01.01.2020 ein Dienstag.',
        'Im Jahr 2024 sind wir umgezogen.',
        'Die Lösung ist 42.',
        'Ergebnis: 3,14159 mal pi.',
        'Kapitel 12, Seite 345.',
        'Ich brauche 100 g Mehl und 200 ml Milch.',
    ])('keine Telefon-Warnung: %s', (text) => {
        expect(cats(text)).not.toContain('telefon')
    })

    it('eine kurze Zahlenfolge ist keine Telefonnummer', () => {
        // 0815 hat nur 4 Ziffern → unter der Schwelle (min. 7).
        expect(scanStructured('Standard-0815-Lösung')).toEqual([])
    })

    it('leerer Text → []', () => {
        expect(scanStructured('')).toEqual([])
    })
})

describe('scanStructured — kombiniert & sortiert', () => {
    it('E-Mail + Telefon im selben Text, nach Position sortiert', () => {
        const text = 'Mail an a@b.de oder ruf 0151 12345678 an'
        const spans = scanStructured(text)
        expect(spans.map((s) => s.category)).toEqual(['email', 'telefon'])
        expect(spans[0].start).toBeLessThan(spans[1].start)
    })

    it('reiner Sachtext ohne strukturierte PII → []', () => {
        expect(scanStructured('Erklär mir die Photosynthese in einfachen Worten.')).toEqual([])
    })
})
