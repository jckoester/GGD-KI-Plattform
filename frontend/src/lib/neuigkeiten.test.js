import { describe, expect, it, vi } from "vitest"
import { alleSchliessen, aufteilen, OFFEN, schliessen } from "./neuigkeiten.js"

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

describe("Hinweise verdichten", () => {
    const fuenf = ["a", "b", "c", "d", "e"].map((id) => ({ id }))

    it("lässt die neuesten offen und legt den Rest darunter", () => {
        const { offen, weitere } = aufteilen(fuenf)
        expect(offen.map((n) => n.id)).toEqual(["a", "b"])
        expect(weitere.map((n) => n.id)).toEqual(["c", "d", "e"])
        expect(OFFEN).toBe(2)
    })

    it("hat bei wenigen Hinweisen keine weiteren", () => {
        expect(aufteilen(fuenf.slice(0, 2)).weitere).toEqual([])
        expect(aufteilen(null)).toEqual({ offen: [], weitere: [] })
    })

    it("schließt alle nacheinander, auch wenn einer scheitert", async () => {
        const reihenfolge = []
        const merken = vi.fn(async (id) => {
            reihenfolge.push(id)
            if (id === "b") throw new Error("offline")
        })
        expect(await alleSchliessen(fuenf.slice(0, 3), merken)).toEqual([])
        expect(reihenfolge).toEqual(["a", "b", "c"])
    })
})
