// @vitest-environment jsdom
/**
 * Zoom für große Diagramme (0.41, Schritt 8). Kein Komponententest — das Projekt mountet keine
 * Svelte-Komponenten —, sondern die Annahme, auf der `ZoomFlaeche.svelte` steht: Peles
 * `enableZoom` arbeitet mit jedem fertigen SVG und hängt mit `always` deutsche Knöpfe an.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { masseAlsZahl, zoomAnhaengen } from "./zoom.js"

const LABELS = { zoomIn: "Vergrößern", zoomOut: "Verkleinern", reset: "Zurücksetzen" }

describe("Zoom für Diagramme", () => {
    it("enableZoom auf einem fertigen SVG zeigt die Knöpfe", async () => {
        globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
        const { enableZoom } = await import("pele/lazy")
        const div = document.createElement("div")
        div.innerHTML = '<svg viewBox="0 0 800 200" width="800" height="200"><rect width="800" height="200"/></svg>'
        document.body.appendChild(div)

        const zoom = enableZoom(div, { always: true, controls: true, labels: LABELS })

        const leiste = div.querySelector(".pele-zoom")
        expect(leiste).not.toBeNull()
        expect(leiste.outerHTML).toContain("Vergrößern")
        zoom.destroy()
        div.remove()
    })

    it("Produktansicht und Chat nutzen denselben Helfer", () => {
        const lesen = (datei) => readFileSync(join(import.meta.dirname, "components", datei), "utf8")
        expect(lesen("ZoomFlaeche.svelte")).toContain("zoomAnhaengen(flaeche, { immer })")
        // Im Chat ohne `immer`: Knöpfe nur an Diagrammen, die nicht hineinpassen.
        expect(lesen("MessageBubble.svelte")).toContain("zoomAnhaengen(block)")
    })

    it("pt-Maße (matplotlib) werden zu Zahlen — sonst bleibt Pele stumm", () => {
        const div = document.createElement("div")
        div.innerHTML = '<svg width="216pt" height="432pt" viewBox="0 0 216 432"></svg>'
        masseAlsZahl(div.firstElementChild)
        expect(div.firstElementChild.getAttribute("width")).toBe("288")
        expect(div.firstElementChild.getAttribute("height")).toBe("576")
    })

    it("ohne Maße aus der viewBox, Zahlen bleiben unberührt", () => {
        const div = document.createElement("div")
        div.innerHTML = '<svg viewBox="0 0 615 921"></svg><svg width="305" height="324"></svg>'
        const [ohne, mit] = div.children
        masseAlsZahl(ohne)
        masseAlsZahl(mit)
        expect([ohne.getAttribute("width"), ohne.getAttribute("height")]).toEqual(["615", "921"])
        expect([mit.getAttribute("width"), mit.getAttribute("height")]).toEqual(["305", "324"])
    })

    it("zoomAnhaengen zeigt an einem pt-Diagramm die Knöpfe", async () => {
        globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
        const div = document.createElement("div")
        div.innerHTML = '<svg width="216pt" height="432pt" viewBox="0 0 216 432"><rect width="10" height="10"/></svg>'
        document.body.appendChild(div)
        const zoom = await zoomAnhaengen(div, { immer: true })
        expect(div.querySelector(".pele-zoom")?.outerHTML).toContain("Vergrößern")
        zoom.destroy()
        div.remove()
    })
})
