/**
 * Eingabezeile des Chats auf kleinem und berührbarem Bildschirm (0.15.1) — Regeln,
 * Messung und Verdrahtung in der Chatseite.
 */
import { describe, it, expect, vi, afterEach } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { get } from "svelte/store"
import {
    ENTER_OPTIONEN,
    KOMPAKT_UNTER_PX,
    enterModus,
    enterSendet,
    istKompakt,
    tastenAktion,
    zeilenMax,
} from "./chat_eingabe.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const lies = (pfad) => readFileSync(join(SRC, pfad), "utf8")

const enter = (extra = {}) => ({ key: "Enter", ...extra })

describe("Enter-Taste", () => {
    it("liest den Modus aus den Einstellungen, Unbekanntes gilt als automatisch", () => {
        expect(enterModus(undefined)).toBe("auto")
        expect(enterModus({})).toBe("auto")
        expect(enterModus({ chat_enter: "quatsch" })).toBe("auto")
        expect(enterModus({ chat_enter: "zeile" })).toBe("zeile")
        expect(ENTER_OPTIONEN.map((o) => o.value)).toEqual(["auto", "senden", "zeile"])
    })

    it("automatisch: am Computer sendet Enter, mit Finger gibt es eine neue Zeile", () => {
        expect(tastenAktion(enter(), { modus: "auto", beruehrung: false })).toBe("senden")
        expect(tastenAktion(enter(), { modus: "auto", beruehrung: true })).toBeNull()
    })

    it("feste Modi gelten unabhängig vom Gerät", () => {
        for (const beruehrung of [true, false]) {
            expect(tastenAktion(enter(), { modus: "senden", beruehrung })).toBe("senden")
            expect(tastenAktion(enter(), { modus: "zeile", beruehrung })).toBeNull()
        }
    })

    it("Umschalt+Enter ist immer eine neue Zeile", () => {
        expect(tastenAktion(enter({ shiftKey: true }), { modus: "senden", beruehrung: false })).toBeNull()
    })

    it("Strg+Enter und ⌘+Enter senden immer — auch im Modus „neue Zeile“", () => {
        expect(tastenAktion(enter({ ctrlKey: true }), { modus: "zeile", beruehrung: true })).toBe("senden")
        expect(tastenAktion(enter({ metaKey: true }), { modus: "auto", beruehrung: true })).toBe("senden")
    })

    it("während einer Eingabemethode bestätigt Enter das Wort und sendet nicht", () => {
        expect(tastenAktion(enter({ isComposing: true }), { modus: "senden", beruehrung: false })).toBeNull()
        expect(tastenAktion(enter({ keyCode: 229 }), { modus: "senden", beruehrung: false })).toBeNull()
        expect(tastenAktion(enter({ isComposing: true, metaKey: true }), { modus: "senden", beruehrung: false })).toBeNull()
    })

    it("andere Tasten lösen nichts aus", () => {
        expect(tastenAktion({ key: "a" }, { modus: "senden", beruehrung: false })).toBeNull()
    })

    it("die Bildschirmtastatur beschriftet Enter passend", () => {
        expect(enterSendet("auto", true)).toBe(false)
        expect(enterSendet("auto", false)).toBe(true)
    })
})

describe("Verdichtung", () => {
    it("greift nur bei gemessener, knapper Höhe", () => {
        expect(istKompakt(null)).toBe(false)
        expect(istKompakt(350)).toBe(true)
        expect(istKompakt(KOMPAKT_UNTER_PX - 1)).toBe(true)
        expect(istKompakt(KOMPAKT_UNTER_PX)).toBe(false)
        expect(istKompakt(900)).toBe(false)
    })

    it("das Textfeld wächst verdichtet auf 3 statt 6 Zeilen", () => {
        expect(zeilenMax(false)).toBe(6)
        expect(zeilenMax(true)).toBe(3)
    })
})

describe("sichtbare Höhe", () => {
    afterEach(() => {
        vi.unstubAllGlobals()
        vi.resetModules()
    })

    function stubBrowser({ vvHoehe, innerHeight = 1000 }) {
        const hoerer = {}
        const stil = {}
        const vv = vvHoehe == null ? undefined : {
            height: vvHoehe,
            addEventListener: (typ, f) => (hoerer[typ] = f),
            removeEventListener: (typ) => delete hoerer[typ],
        }
        vi.stubGlobal("window", {
            visualViewport: vv,
            innerHeight,
            addEventListener: (typ, f) => (hoerer[typ] = f),
            removeEventListener: (typ) => delete hoerer[typ],
        })
        vi.stubGlobal("document", {
            documentElement: {
                style: {
                    setProperty: (k, v) => (stil[k] = v),
                    removeProperty: (k) => delete stil[k],
                },
            },
        })
        return { hoerer, stil, vv }
    }

    it("folgt dem sichtbaren Ausschnitt, nicht der Layouthöhe", async () => {
        const { hoerer, stil, vv } = stubBrowser({ vvHoehe: 380, innerHeight: 1000 })
        const { sichtbareHoehe } = await import("./stores/geraet.js")
        const werte = []
        const ab = sichtbareHoehe.subscribe((h) => werte.push(h))
        expect(werte.at(-1)).toBe(380)
        expect(stil["--sichtbare-hoehe"]).toBe("380px")

        vv.height = 700
        hoerer.resize()
        expect(werte.at(-1)).toBe(700)

        ab()
        expect(stil["--sichtbare-hoehe"]).toBeUndefined()
        expect(hoerer.resize).toBeUndefined()
    })

    it("ohne visualViewport gilt innerHeight", async () => {
        stubBrowser({ vvHoehe: null, innerHeight: 640 })
        const { sichtbareHoehe } = await import("./stores/geraet.js")
        expect(get(sichtbareHoehe)).toBe(640)
    })
})

describe("Chatseite", () => {
    const SEITE = lies("routes/(app)/chat/+page.svelte")

    it("entscheidet Enter über tastenAktion statt fest „Enter ohne Umschalt“", () => {
        expect(SEITE).toMatch(/const aktion = tastenAktion\(e, \{\s*modus: enterModusWert,\s*beruehrung: \$grobZeiger,/)
        expect(SEITE).not.toMatch(/e\.key === "Enter" && !e\.shiftKey\) \{\s*e\.preventDefault\(\);\s*if \(subjectPickerOpen/)
    })

    it("beschriftet die Enter-Taste der Bildschirmtastatur", () => {
        expect(SEITE).toMatch(/enterkeyhint=\{enterSendet\(enterModusWert, \$grobZeiger\)/)
    })

    it("begrenzt das Textfeld verdichtet und blendet Modellzeile, Kosten und Legende aus", () => {
        expect(SEITE).toMatch(/Math\.min\(Math\.ceil\(textarea\.scrollHeight \/ 24\), zeilenMax\(kompakt\)\)/)
        expect(SEITE).toMatch(/flex flex-wrap items-center gap-x-3 gap-y-1 \{kompakt\s*\?\s*'hidden'/)
        expect(SEITE).toMatch(/\{#if !kompakt && \(granularity === "conversation"/)
        expect(SEITE).toMatch(/\{kompakt \? '' : 'sm:block'\}/)
    })
})

describe("Höhendeckel an der sichtbaren Höhe", () => {
    it.each([
        ["lib/components/ContextChips.svelte"],
        ["lib/components/ContextSuggestions.svelte"],
    ])("%s rechnet mit --sichtbare-hoehe statt dvh", (pfad) => {
        const quelle = lies(pfad)
        expect(quelle).toMatch(/max-h-\[calc\(var\(--sichtbare-hoehe,100dvh\)\*0\.\d+\)\]/)
        expect(quelle).not.toMatch(/max-h-\[\d+dvh\]/)
    })
})

describe("Profil", () => {
    it("bietet die Enter-Einstellung an", () => {
        const SEITE = lies("routes/(app)/profile/+page.svelte")
        expect(SEITE).toMatch(/updatePreference\(ENTER_SCHLUESSEL, e\.target\.value\)/)
        expect(SEITE).toMatch(/\{#each ENTER_OPTIONEN as/)
    })
})
