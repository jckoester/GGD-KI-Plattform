import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { get } from "svelte/store"
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"

vi.mock("$lib/api.js", () => ({ getCalendarStatus: vi.fn() }))

import { getCalendarStatus } from "$lib/api.js"

/** Frisches Modul je Test — der Store puffert absichtlich über seine Lebensdauer. */
async function frisch() {
    vi.resetModules()
    return import("./calendarStatus.js")
}

beforeEach(() => vi.mocked(getCalendarStatus).mockReset())
afterEach(() => vi.restoreAllMocks())

describe("ensureCalendarStatus", () => {
    it("fragt einmal und merkt sich die Antwort", async () => {
        vi.mocked(getCalendarStatus).mockResolvedValue({ configured: true })
        const { ensureCalendarStatus, calendarConfigured } = await frisch()

        await ensureCalendarStatus()
        await ensureCalendarStatus()

        expect(getCalendarStatus).toHaveBeenCalledTimes(1)
        expect(get(calendarConfigured)).toBe(true)
    })

    it("fragt auch dann nicht erneut, wenn keine Quelle eingerichtet ist", async () => {
        // `configured: false` ist eine Antwort, kein fehlender Zustand — sonst fragte
        // jede Öffnung des Dialogs neu.
        vi.mocked(getCalendarStatus).mockResolvedValue({ configured: false })
        const { ensureCalendarStatus } = await frisch()

        await ensureCalendarStatus()
        await ensureCalendarStatus()

        expect(getCalendarStatus).toHaveBeenCalledTimes(1)
    })

    it("bleibt nach einem Netzwerkfehler fragend", async () => {
        // `refreshCalendarStatus` schluckt Fehler absichtlich. Dann darf der Zustand
        // aber nicht als „beantwortet" gelten — sonst bliebe der Knopf bis zum Neuladen
        // der Seite weg, weil einmal das Netz klemmte.
        vi.mocked(getCalendarStatus).mockRejectedValue(new Error("offline"))
        const { ensureCalendarStatus } = await frisch()

        await ensureCalendarStatus()
        await ensureCalendarStatus()

        expect(getCalendarStatus).toHaveBeenCalledTimes(2)
    })
})

// ── Wächter: Wer den Status liest, muss ihn auch laden ───────────────────────

const SRC = dirname(dirname(dirname(fileURLToPath(import.meta.url)))) // stores → lib → src

/** Kommentare entfernen, bevor sie als Code zählen.
 *
 * Ohne das findet der Wächter seine eigene Erklärung: Die Gegenprobe (Lader ausbauen,
 * Kommentar stehen lassen) blieb grün, weil im Kommentar `ensureCalendarStatus` steht.
 * Derselbe Fehler wie bei `farbregeln.test.js` und dem Picker-Wächter — ein Wächter darf
 * nicht messen, was über ihn geschrieben steht.
 */
const ohneKommentare = (text) =>
    text
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/[^\n]*/gm, "")
        .replace(/<!--[\s\S]*?-->/g, "")

function quelldateien(wurzel) {
    const gefunden = []
    for (const eintrag of readdirSync(wurzel)) {
        const pfad = join(wurzel, eintrag)
        if (statSync(pfad).isDirectory()) gefunden.push(...quelldateien(pfad))
        else if (/\.(svelte|js)$/.test(eintrag) && !/\.test\.js$/.test(eintrag))
            gefunden.push(pfad)
    }
    return gefunden
}

describe("Wer den Kalenderstatus liest, lädt ihn auch", () => {
    it("kein Leser ohne Lader", () => {
        // Der Fehler vom 14.09.2026: `PatternEditor` las `$calendarConfigured`, geladen
        // wurde der Status aber nur in der Admin-Seitenleiste und auf `/settings` — beide
        // in der `(admin)`-Routengruppe. Auf dem Jahresplan blieb der Store auf seinem
        // Anfangswert `configured: null`, und der Knopf „Aus Stundenplan übernehmen"
        // erschien nie. Kein Fehler, keine Meldung — die Funktion war schlicht unsichtbar.
        const dateien = quelldateien(SRC).filter(
            (p) => !p.endsWith(join("stores", "calendarStatus.js")),
        )
        expect(dateien.length).toBeGreaterThan(50) // der Lauf hat wirklich gesucht

        const ohneLader = []
        for (const pfad of dateien) {
            const inhalt = ohneKommentare(readFileSync(pfad, "utf8"))
            const liest = /\$calendarConfigured|\$calendarStatus/.test(inhalt)
            const laedt = /ensureCalendarStatus|refreshCalendarStatus/.test(inhalt)
            if (liest && !laedt) ohneLader.push(pfad.replace(SRC, "src"))
        }

        expect(ohneLader).toEqual([])
    })

    it("entfernt Kommentare, bevor sie als Lader zählen", () => {
        const nurKommentar = `
            // ensureCalendarStatus() stand hier mal
            /* und refreshCalendarStatus() hier */
            <!-- und ensureCalendarStatus hier -->
        `
        expect(ohneKommentare(nurKommentar).trim()).toBe("")
    })
})
