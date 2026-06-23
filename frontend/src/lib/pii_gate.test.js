import { describe, it, expect, vi, beforeEach } from "vitest"

// Server-Call mocken — die Client-Regex (pii_client.js) bleibt echt.
vi.mock("./api.js", () => ({ scanPii: vi.fn() }))

import { scanPii } from "./api.js"
import { scanForPii } from "./pii_gate.js"

describe("scanForPii — Fail-open & Timeout (Schritt 6)", () => {
    beforeEach(() => {
        vi.clearAllMocks()
        // Erwartetes Fail-open-Logging stumm schalten (Test-Hygiene).
        vi.spyOn(console, "error").mockImplementation(() => {})
        vi.spyOn(console, "warn").mockImplementation(() => {})
    })

    it("Server-Fehler → nur Client-Spans, kein Wurf", async () => {
        scanPii.mockRejectedValueOnce(new Error("500 Internal"))
        const spans = await scanForPii("Schreib mir an a@b.de")
        expect(spans.map((s) => s.category)).toEqual(["email"])
    })

    it("Timeout: hängender Server wird abgebrochen → nur Client-Spans", async () => {
        // Server löst nie auf, bricht aber auf das Abort-Signal hin ab.
        scanPii.mockImplementation(
            (_text, opts) =>
                new Promise((_resolve, reject) => {
                    opts?.signal?.addEventListener("abort", () => {
                        const e = new Error("aborted")
                        e.name = "AbortError"
                        reject(e)
                    })
                }),
        )
        const spans = await scanForPii("Ruf 0151 12345678 an", { timeoutMs: 10 })
        expect(spans.map((s) => s.category)).toEqual(["telefon"])
    })

    it("Server-Treffer (Name) wird mit Client-Treffer (E-Mail) kombiniert & sortiert", async () => {
        scanPii.mockResolvedValueOnce({
            spans: [{ category: "name", start: 0, end: 3, text: "Max" }],
        })
        const spans = await scanForPii("Max — mail a@b.de")
        expect(spans.map((s) => s.category)).toEqual(["name", "email"])
        expect(spans[0].start).toBeLessThan(spans[1].start)
    })

    it("leeres spans-Feld vom Server → nur Client-Spans", async () => {
        scanPii.mockResolvedValueOnce({ spans: [] })
        const spans = await scanForPii("IBAN DE89 3704 0044 0532 0130 00")
        expect(spans.map((s) => s.category)).toEqual(["iban"])
    })

    it("kein Treffer in keiner Schicht → []", async () => {
        scanPii.mockResolvedValueOnce({ spans: [] })
        expect(await scanForPii("Erklär mir die Photosynthese.")).toEqual([])
    })
})
