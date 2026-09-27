import { describe, it, expect, beforeEach, vi } from "vitest"
import { get } from "svelte/store"

vi.mock("$lib/api.js", () => ({ patchPreferences: vi.fn(async () => {}) }))

const { user } = await import("./user.js")
const { KACHELN, schalteKachel, sichtbareKacheln, zeigtKachel } = await import(
    "./startkacheln.js"
)

beforeEach(() => user.set({ preferences: {} }))

describe("Startkacheln", () => {
    it("zeigt ohne Einstellung alle", () => {
        expect(get(sichtbareKacheln).map((k) => k.id)).toEqual(
            KACHELN.map((k) => k.id),
        )
    })

    it("speichert das Ausblenden, nicht das Einblenden", async () => {
        // ⚠️ Die Richtung ist der Kern: Eine Liste der **sichtbaren** Kacheln müsste bei
        // jeder neuen nachgezogen werden — wer einmal eingestellt hat, bekäme spätere
        // Kacheln nie zu sehen.
        const { patchPreferences } = await import("$lib/api.js")
        await schalteKachel("gruppen", false)
        expect(patchPreferences).toHaveBeenCalledWith({ startkacheln_aus: ["gruppen"] })
        expect(get(zeigtKachel)("gruppen")).toBe(false)
        expect(get(zeigtKachel)("heute")).toBe(true)
    })

    it("eine neue Kachel erscheint auch bei bestehender Einstellung", () => {
        user.set({ preferences: { startkacheln_aus: ["gruppen"] } })
        // „heute" und „naechster" bleiben sichtbar, obwohl nie eingestellt.
        expect(get(sichtbareKacheln).map((k) => k.id)).toEqual(["heute", "naechster"])
    })

    it("blendet wieder ein", async () => {
        user.set({ preferences: { startkacheln_aus: ["heute"] } })
        await schalteKachel("heute", true)
        expect(get(zeigtKachel)("heute")).toBe(true)
    })

    it("die Reihenfolge ist fest", () => {
        // Entscheidung F3: keine Sortierung. Die Reihenfolge ist Teil der Gestaltung.
        expect(KACHELN.map((k) => k.id)).toEqual(["heute", "naechster", "gruppen"])
    })
})
