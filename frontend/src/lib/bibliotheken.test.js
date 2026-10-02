/**
 * `/about` nennt alle direkten Abhängigkeiten (0.12) — und bleibt dabei.
 *
 * Bis 0.12 war die Liste eine Auswahl, die niemand nachzog: Von elf
 * Laufzeitabhängigkeiten des Frontends standen drei darin, von den Backend-Paketen
 * sieben. Dieser Test gleicht in beide Richtungen ab — keine Abhängigkeit ohne
 * Eintrag, kein Eintrag ohne Abhängigkeit.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { BIBLIOTHEKEN } from './bibliotheken.js'

const FRONTEND = dirname(dirname(dirname(fileURLToPath(import.meta.url))))
const WURZEL = join(FRONTEND, '..')

// `svelte-check` ist ein Prüfwerkzeug und steht nur versehentlich bei den
// Laufzeitabhängigkeiten (Todo „svelte-check und Testwerkzeuge", 02.10.2026).
const FRONTEND_KEINE_BIBLIOTHEK = ['svelte-check']
// Testwerkzeuge in requirements.txt — dieselbe Todo-Notiz.
const BACKEND_KEINE_BIBLIOTHEK = ['pytest', 'pytest-asyncio', 'pytest-httpx', 'pyflakes']

const json = (pfad) => JSON.parse(readFileSync(pfad, 'utf8'))
const norm = (name) => name.toLowerCase().replace(/_/g, '-')

function requirements() {
    return readFileSync(join(WURZEL, 'backend', 'requirements.txt'), 'utf8')
        .split('\n')
        .map((z) => z.replace(/#.*/, '').trim())
        .filter(Boolean)
        .map((z) => norm(z.split(/[\s[<>=@;!~]/)[0]))
}

function gelistet(quelle) {
    return BIBLIOTHEKEN.find((g) => g.quelle === quelle).eintraege.map((e) => norm(e.paket))
}

describe('Verwendete Bibliotheken auf /about', () => {
    it('Frontend: jede Laufzeitabhängigkeit steht in der Liste', () => {
        const pkg = json(join(FRONTEND, 'package.json'))
        const fehlt = Object.keys(pkg.dependencies)
            .filter((d) => !FRONTEND_KEINE_BIBLIOTHEK.includes(d))
            .filter((d) => !gelistet('frontend').includes(norm(d)))
        expect(fehlt).toEqual([])
    })

    it('Frontend: kein Eintrag ohne Paket', () => {
        const pkg = json(join(FRONTEND, 'package.json'))
        const alle = Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }).map(norm)
        expect(gelistet('frontend').filter((p) => !alle.includes(p))).toEqual([])
    })

    it('Backend: jede Abhängigkeit aus requirements.txt steht in der Liste — und umgekehrt', () => {
        const req = requirements().filter((r) => !BACKEND_KEINE_BIBLIOTHEK.includes(r))
        expect(req.filter((r) => !gelistet('backend').includes(r))).toEqual([])
        expect(gelistet('backend').filter((p) => !req.includes(p))).toEqual([])
    })

    it('Render-Sidecar: beide Richtungen', () => {
        const deps = Object.keys(json(join(WURZEL, 'render-sidecar', 'package.json')).dependencies).map(norm)
        expect(deps.filter((d) => !gelistet('sidecar').includes(d))).toEqual([])
        expect(gelistet('sidecar').filter((p) => !deps.includes(p))).toEqual([])
    })

    it('jeder Eintrag hat Namen und Lizenz', () => {
        const ohne = BIBLIOTHEKEN.flatMap((g) => g.eintraege).filter((e) => !e.name || !e.lizenz)
        expect(ohne).toEqual([])
    })
})
