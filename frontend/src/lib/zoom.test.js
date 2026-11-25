// @vitest-environment jsdom
/**
 * Zoom für große Diagramme (0.41, Schritt 8). Kein Komponententest — das Projekt mountet keine
 * Svelte-Komponenten —, sondern die Annahme, auf der `ZoomFlaeche.svelte` steht: Peles
 * `enableZoom` arbeitet mit jedem fertigen SVG und hängt mit `always` deutsche Knöpfe an.
 */
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { masseAlsZahl, viewBoxAufNull, zoomAnhaengen } from "./zoom.js"

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

// 0.58.1: Schaltpläne im Chat blieben leer. Das SVG von Prod (Batterie, Glühlampe, zwei
// Widerstände), wie node-tikzjax es liefert — Ausschnitt ab −72/−72, anderer Maßstab als die Größe.
const SCHALTPLAN = '<svg xmlns="http://www.w3.org/2000/svg" width="76.407" height="109.87" viewBox="-72 -72 57.305 82.403">'
    + '<g stroke="#000" stroke-miterlimit="10" stroke-width=".4"><path fill="none" d="M-72.07-2.218h.2m-.2 0h22.478"/>'
    + '<g stroke-width=".8"><path fill="none" d="M-43.617-46.376c7.04 0 12.747-5.707 12.747-12.747"/></g></g></svg>'

/** Wohin ein Punkt der Zeichnung im neuen Ausschnitt fällt (scale … translate … der Gruppe). */
function abgebildet(svg, x, y) {
    const t = svg.firstElementChild.getAttribute("transform")
    const [sx, sy, tx, ty] = t.match(/-?[\d.]+(?:e-?\d+)?/g).map(Number)
    return [sx * (x + tx), sy * (y + ty)]
}

describe("Ausschnitt vor dem Zoom (0.58.1)", () => {
    it("legt einen CircuiTikZ-Schaltplan auf 0 0 Breite Höhe, ohne das Bild zu verschieben", () => {
        const div = document.createElement("div")
        div.innerHTML = SCHALTPLAN
        const svg = div.firstElementChild
        viewBoxAufNull(svg)
        expect(svg.getAttribute("viewBox")).toBe("0 0 76.407 109.87")
        expect(svg.children).toHaveLength(1)
        expect(svg.querySelectorAll("path")).toHaveLength(2)
        // Die Ecken des alten Ausschnitts sind die Ecken des neuen
        const [x0, y0] = abgebildet(svg, -72, -72)
        const [x1, y1] = abgebildet(svg, -72 + 57.305, -72 + 82.403)
        expect([x0, y0]).toEqual([0, 0])
        expect(x1).toBeCloseTo(76.407, 3)
        expect(y1).toBeCloseTo(109.87, 3)
    })

    it("ein zweiter Aufruf und SVGs ab 0,0 bleiben unverändert", () => {
        const div = document.createElement("div")
        div.innerHTML = SCHALTPLAN + '<svg width="800" height="200" viewBox="0 0 800 200"><rect width="8" height="2"/></svg>'
        const [schaltplan, mermaid] = div.children
        viewBoxAufNull(schaltplan)
        const einmal = schaltplan.outerHTML
        viewBoxAufNull(schaltplan)
        expect(schaltplan.outerHTML).toBe(einmal)
        const vorher = mermaid.outerHTML
        viewBoxAufNull(mermaid)
        expect(mermaid.outerHTML).toBe(vorher)
    })

    it("ohne brauchbare Maße oder viewBox geschieht nichts", () => {
        const div = document.createElement("div")
        div.innerHTML = '<svg viewBox="-5 -5 10 10"><rect/></svg><svg width="10" height="10"><rect/></svg>'
        for (const svg of div.children) {
            const vorher = svg.outerHTML
            viewBoxAufNull(svg)
            expect(svg.outerHTML).toBe(vorher)
        }
    })

    it("nach zoomAnhaengen liegt die Zeichnung im sichtbaren Ausschnitt", async () => {
        globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
        const div = document.createElement("div")
        div.innerHTML = SCHALTPLAN
        document.body.appendChild(div)
        const zoom = await zoomAnhaengen(div, { immer: true })
        const svg = div.querySelector("svg")
        // Pele setzt `0 0 width height` — das ist jetzt derselbe Ausschnitt
        expect(svg.getAttribute("viewBox")).toBe("0 0 76.407 109.87")
        const [x, y] = abgebildet(svg, -43.617, -46.376)
        expect(x).toBeGreaterThan(0)
        expect(x).toBeLessThan(76.407)
        expect(y).toBeGreaterThan(0)
        expect(y).toBeLessThan(109.87)
        zoom.destroy()
        div.remove()
    })
})
