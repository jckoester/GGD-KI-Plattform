/**
 * Der Chip für verlinktes Vokabular im Stundenentwurf (Paket 5, AP7).
 *
 * ⚠️ **Am Quelltext, weil es um ein Element geht, nicht um Logik.** Ob ein `<span>` oder
 * ein `<a>` dasteht, entscheidet darüber, ob die Lehrkraft aus der Planung zur Erklärung
 * kommt — und genau diese Sorte Unterschied hat am 24.09.2026 schon zweimal zugeschlagen
 * (toter Stundentitel, verschluckte Schraffur).
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const CHIP = readFileSync(
    join(SRC, "lib/components/planner/LinkedTermInput.svelte"), "utf8",
)

describe("Verlinktes Vokabular im Stundenentwurf", () => {
    it("⚠️ führt zur Beschreibung des Knotens", () => {
        // Vorher ein `<span>`: Die Lehrkraft wählte „Placemat" und kam aus der Planung
        // nicht zur Erklärung — obwohl jede Methode eine Kurzbeschreibung trägt.
        const block = CHIP.slice(CHIP.indexOf("{#if isNode}"))
        const bis = block.slice(0, block.indexOf("{:else}"))
        expect(bis).toMatch(/<a\s+href=\{`\/knowledge\/\$\{value\.node_id\}`\}/)
    })

    it("⚠️ öffnet in einem neuen Tab", () => {
        // Der Stundenentwurf kann ungespeicherte Eingaben tragen; ein Wechsel im selben
        // Tab verlöre sie. `rel=noopener` gehört dazu.
        const block = CHIP.slice(CHIP.indexOf("{#if isNode}"))
        const bis = block.slice(0, block.indexOf("{:else}"))
        expect(bis).toContain('target="_blank"')
        expect(bis).toContain('rel="noopener"')
    })

    it("lässt das Entfernen unangetastet", () => {
        // Der Link darf die vorhandene Bedienung nicht verdrängen.
        const block = CHIP.slice(CHIP.indexOf("{#if isNode}"))
        const bis = block.slice(0, block.indexOf("{:else}"))
        expect(bis).toContain('aria-label="Auswahl entfernen"')
    })
})
