import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { speicherText, textDateiname } from "./produktleiste.js"

const SRC = join(import.meta.dirname, "..")

describe("Produktleiste: Wörter (0.41, Schritt 7)", () => {
    it("ein Zustand, ein Wort — Knopf und Titel", () => {
        expect(speicherText("idle")).toBe("Speichern")
        expect(speicherText("idle", "titel")).toBe("In der Werkstatt speichern")
        expect(speicherText("exists")).toBe("Schon da")
        expect(speicherText("full", "titel")).toMatch(/Werkstatt voll/)
        expect(speicherText("unbekannt")).toBe("Speichern")
    })

    it("Dateiname einer Textantwort", () => {
        expect(textDateiname("Größen & Einheiten: Übungsblatt")).toBe("grossen-einheiten-ubungsblatt.md")
        expect(textDateiname("")).toBe("antwort.md")
    })
})

describe("Produktleiste: eingebunden (Quelltext-Wächter)", () => {
    const bubble = readFileSync(join(SRC, "lib/components/MessageBubble.svelte"), "utf8")

    it("Bild, Diagramm und Text benutzen dieselbe Leiste", () => {
        expect(bubble.match(/<ProduktLeiste\b/g)).toHaveLength(2)        // Bild, Text
        expect(bubble).toContain("mount(ProduktLeiste, {")             // Diagramm im gerenderten HTML
        expect(bubble).toContain("eingehaengt.forEach((k) => unmount(k))")
    })

    it("keine eigenen Speichern-Knöpfe mehr neben der Leiste", () => {
        expect(bubble).not.toContain("saveBtn")
        expect(bubble).not.toContain("async function saveImage")
    })
})
