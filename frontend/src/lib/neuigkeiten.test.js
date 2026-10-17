import { describe, expect, it, vi } from "vitest"
import { schliessen } from "./neuigkeiten.js"

const LISTE = [{ id: "a", titel: "A" }, { id: "b", titel: "B" }]

describe("Hinweise schließen", () => {
    it("ruft den Endpunkt und blendet den Hinweis aus", async () => {
        const merken = vi.fn().mockResolvedValue(undefined)
        expect(await schliessen(LISTE, "a", merken)).toEqual([{ id: "b", titel: "B" }])
        expect(merken).toHaveBeenCalledWith("a")
    })

    it("blendet auch aus, wenn das Merken scheitert", async () => {
        const merken = vi.fn().mockRejectedValue(new Error("offline"))
        expect(await schliessen(LISTE, "b", merken)).toEqual([{ id: "a", titel: "A" }])
    })

    it("ruft den Endpunkt über die API", async () => {
        const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: true })
        await schliessen(LISTE, "a")
        expect(fetchMock).toHaveBeenCalledWith("/api/neuigkeiten/a/gelesen",
            expect.objectContaining({ method: "POST" }))
        fetchMock.mockRestore()
    })
})
