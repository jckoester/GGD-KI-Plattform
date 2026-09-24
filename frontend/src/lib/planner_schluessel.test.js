/**
 * Die Schlüssel der Jahresplanungs-Tabelle müssen eindeutig sein.
 *
 * ⚠️ **Der Anlass** (Betatest, 23.09.2026): Die Jahresplanung **einer** Klasse erschien
 * gar nicht. Browser-Konsole: `Uncaught Error: https://svelte.dev/e/each_key_duplicate`.
 * Ein geschlüsselter `{#each}`-Block bekam zwei Einträge mit demselben Schlüssel — und
 * Svelte bricht dann das Rendern der **ganzen** Komponente ab, statt einen Eintrag
 * wegzulassen.
 *
 * Der Schlüssel lautete:
 *
 *     item.type === "week" ? item.key : item.type + (item.name ?? item.type)
 *
 * Für Ferien also `"ferien" + Name`. Dieser Test prüft die Eindeutigkeit an den Daten —
 * das Rendern selbst kann er nicht prüfen (keine Komponententests im Projekt), wohl aber
 * die Bedingung, unter der es scheitert.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { groupSlotsByWeek } from "./planner.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))

function slot(id, date) {
    return { id, date, halbjahr: date < "2027-02-01" ? 1 : 2, kategorie: "unterricht" }
}

/** Die Schlüssel, die das Markup aus den Einträgen bildet. */
function schluessel(items) {
    return items.map((i) => i.key)
}

describe("Schlüssel der Wochenliste", () => {
    it("⚠️ ein Ferienblock über zwei Lücken erscheint nur einmal", () => {
        // Liegt ein Termin **innerhalb** der Ferien (Import, Nachschreibtermin,
        // fehlerhaft erzeugter Slot), überlappt derselbe Ferienblock die Lücke davor
        // **und** die dahinter. Die Ferien-Schleife läuft je Lücke — ohne Entdopplung
        // landet er zweimal in der Liste, mit demselben Namen und demselben Schlüssel.
        const items = groupSlotsByWeek(
            [slot("a", "2026-12-15"), slot("b", "2026-12-29"), slot("c", "2027-01-19")],
            { ferien: [{ name: "Weihnachtsferien", von: "2026-12-23", bis: "2027-01-08" }] },
        )
        const ferien = items.filter((i) => i.type === "ferien")
        expect(ferien.length, "Ferienblock doppelt eingefügt").toBe(1)
    })

    it("⚠️ zwei Ferien mit demselben Namen kollidieren nicht", () => {
        // „Bewegliche Ferientage" stehen in manchen Kalendern mehrfach.
        const items = groupSlotsByWeek(
            [slot("a", "2026-10-05"), slot("b", "2026-11-09"), slot("c", "2026-12-07")],
            {
                ferien: [
                    { name: "Bewegliche Ferientage", von: "2026-10-26", bis: "2026-10-30" },
                    { name: "Bewegliche Ferientage", von: "2026-11-16", bis: "2026-11-20" },
                ],
            },
        )
        const k = schluessel(items)
        expect(new Set(k).size, `doppelte Schlüssel: ${k}`).toBe(k.length)
    })

    it("jeder Eintrag trägt einen Schlüssel", () => {
        // Ohne eigenen Schlüssel müsste das Markup wieder einen bauen — und genau dabei
        // ist der Fehler entstanden.
        const items = groupSlotsByWeek(
            [slot("a", "2026-10-05"), slot("b", "2027-03-01")],
            {
                ferien: [{ name: "Herbstferien", von: "2026-10-26", bis: "2026-10-30" }],
                halbjahreswechsel: "2027-02-01",
            },
        )
        expect(items.every((i) => typeof i.key === "string" && i.key.length)).toBe(true)
        const k = schluessel(items)
        expect(new Set(k).size).toBe(k.length)
    })

    it("Wochen behalten ihren Schlüssel `JJJJ-Wnn`", () => {
        // ⚠️ `PlannerTable` vergleicht ihn mit `currentWeekKey()`, um beim Öffnen zur
        // aktuellen Woche zu scrollen. Ein anderes Format bräche das lautlos.
        const items = groupSlotsByWeek([slot("a", "2026-10-05")], {})
        const woche = items.find((i) => i.type === "week")
        expect(woche.key).toMatch(/^\d{4}-W\d{2}$/)
    })
})

describe("Markup der Wochenliste (Quelltext-Wächter)", () => {
    it("⚠️ baut den Schlüssel nicht mehr selbst", () => {
        // Er gehört zu den Daten: `groupSlotsByWeek` weiß, was ein Eintrag ist, das
        // Markup nicht. Der alte Ausdruck `item.type + (item.name ?? item.type)` hat
        // die ganze Jahresplanung einer Klasse unsichtbar gemacht.
        const tabelle = readFileSync(
            join(SRC, "lib/components/planner/PlannerTable.svelte"), "utf8")
        // ⚠️ Nur die positive Zusage. Eine Gegenprobe auf den alten Ausdruck müsste den
        // Kommentar daneben ausblenden, der ihn zitiert — ein Wächter, der auf die
        // Begründung anspringt, meldet jede gute Dokumentation als Fehler.
        expect(tabelle).toContain("{#each weekItems as item (item.key)}")
    })
})
