/**
 * Wächter: Wo das Schulkonto die Mitglieder führt, gibt es keinen Beitrittscode.
 *
 * **Warum das eine Zusage ist, kein Geschmack.** Zwei Wege in dieselbe Gruppe hießen
 * zwei Wahrheiten über die Mitgliedschaft — und der Immediate Mirror räumt nur die eine
 * Sorte ab. Die Vererbung aus der Klasse ist bei SSO-Gruppen aus demselben Grund
 * abgeschaltet.
 *
 * Geprüft wird am Quelltext, weil das Projekt keine Svelte-Komponententests hat (siehe
 * `picker_tastatur.test.js`).
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url))) // src/lib → src
const KOMPONENTE = join(SRC, "lib/components/BeitrittsCode.svelte")
const GRUPPENSEITE = join(SRC, "routes/(app)/subjects/[slug]/groups/[id]/+page.svelte")

const lies = (p) => readFileSync(p, "utf8")

describe("Beitrittscode bei SSO-geführten Gruppen", () => {
    it("die Komponente kennt den Fall", () => {
        expect(lies(KOMPONENTE)).toMatch(/\{#if ssoGefuehrt\}/)
    })

    it("sie lädt gar nicht erst einen Code", () => {
        // Sonst stünde die Anfrage im Netzwerkprotokoll und die Drossel zählte mit,
        // obwohl es nichts anzuzeigen gibt.
        expect(lies(KOMPONENTE)).toMatch(/if \(!ssoGefuehrt\) lesen\(\)/)
    })

    it("sie sagt, warum kein Code nötig ist", () => {
        // Ein leerer Kasten ohne Erklärung sieht nach einem Fehler aus.
        expect(lies(KOMPONENTE)).toContain("kommen aus dem Schulkonto")
    })

    it("die Gruppenseite reicht die Auskunft durch", () => {
        // ⚠️ Ohne diese Zeile bliebe `ssoGefuehrt` immer `false` — die Komponente wäre
        // richtig und die Regel trotzdem wirkungslos.
        expect(lies(GRUPPENSEITE)).toMatch(/ssoGefuehrt=\{Boolean\(group\.sso_group_id\)\}/)
    })
})
