import { describe, it, expect } from "vitest"
import {
    combinePiiSpans,
    segmentText,
    uniqueCategories,
    shouldScanForPii,
    PII_CATEGORY_LABELS,
} from "./pii_gate.js"

const span = (category, start, end, text = "") => ({ category, start, end, text })

describe("combinePiiSpans", () => {
    it("führt zwei Listen zusammen und sortiert nach Position", () => {
        const client = [span("email", 10, 16)]
        const server = [span("name", 0, 3)]
        expect(combinePiiSpans(client, server).map((s) => s.category)).toEqual([
            "name",
            "email",
        ])
    })

    it("verwirft einen überlappenden späteren Span (Vorrang früher)", () => {
        const a = [span("iban", 0, 22)]
        const b = [span("telefon", 5, 14)] // liegt komplett in der IBAN
        const out = combinePiiSpans(a, b)
        expect(out).toHaveLength(1)
        expect(out[0].category).toBe("iban")
    })

    it("bei gleichem Start gewinnt der längere Span", () => {
        const out = combinePiiSpans([span("name", 0, 4)], [span("wohnort", 0, 10)])
        expect(out).toHaveLength(1)
        expect(out[0].category).toBe("wohnort")
    })

    it("ignoriert null/undefined-Listen", () => {
        expect(combinePiiSpans(null, [span("email", 0, 5)], undefined)).toEqual([
            span("email", 0, 5),
        ])
    })

    it("keine Spans → []", () => {
        expect(combinePiiSpans([], [])).toEqual([])
    })
})

describe("segmentText", () => {
    it("ohne Spans → ein Text-Segment", () => {
        expect(segmentText("nur text", [])).toEqual([
            { text: "nur text", category: null },
        ])
    })

    it("Span in der Mitte → text / pii / text", () => {
        const text = "ich bin Max heute"
        const segs = segmentText(text, [span("name", 8, 11, "Max")])
        expect(segs).toEqual([
            { text: "ich bin ", category: null },
            { text: "Max", category: "name" },
            { text: " heute", category: null },
        ])
    })

    it("Span am Anfang und am Ende", () => {
        const text = "Max wohnt Reutlingen"
        const segs = segmentText(text, [
            span("name", 0, 3, "Max"),
            span("wohnort", 10, 20, "Reutlingen"),
        ])
        expect(segs[0]).toEqual({ text: "Max", category: "name" })
        expect(segs[segs.length - 1]).toEqual({
            text: "Reutlingen",
            category: "wohnort",
        })
    })

    it("Segmente rekonstruieren immer den Originaltext", () => {
        const text = "Max — mail a@b.de jetzt"
        const spans = combinePiiSpans(
            [span("email", 11, 17, "a@b.de")],
            [span("name", 0, 3, "Max")],
        )
        const joined = segmentText(text, spans)
            .map((s) => s.text)
            .join("")
        expect(joined).toBe(text)
    })
})

describe("uniqueCategories", () => {
    it("dedupliziert in Reihenfolge des ersten Auftretens", () => {
        const spans = [
            span("name", 0, 3),
            span("email", 5, 10),
            span("name", 12, 15),
        ]
        expect(uniqueCategories(spans)).toEqual(["name", "email"])
    })

    it("keine Spans → []", () => {
        expect(uniqueCategories([])).toEqual([])
    })
})

describe("shouldScanForPii (Block/Suppress-Entscheidung)", () => {
    it("getippter Text, nicht unterdrückt → true", () => {
        expect(shouldScanForPii({ text: "hallo", suppressed: false })).toBe(true)
    })

    it("leerer Text → false (kein Scan)", () => {
        expect(shouldScanForPii({ text: "", suppressed: false })).toBe(false)
    })

    it("für die Konversation unterdrückt → false", () => {
        expect(shouldScanForPii({ text: "hallo", suppressed: true })).toBe(false)
    })
})

describe("PII_CATEGORY_LABELS", () => {
    it("deckt alle fünf Kategorien mit deutschem Label ab", () => {
        expect(PII_CATEGORY_LABELS).toMatchObject({
            name: "Name",
            wohnort: "Wohnort",
            email: "E-Mail",
            telefon: "Telefon",
            iban: "IBAN",
        })
    })
})
