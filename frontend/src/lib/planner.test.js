import { describe, it, expect } from "vitest"
import { mitPhasenKennungen, entwurfsStand } from "./planner.js"

describe("entwurfsStand", () => {
  it("ohne verknüpften Entwurf: keiner", () => {
    expect(entwurfsStand({ stunde_node_id: null, hat_phasen: false })).toBe("keiner")
  })

  it("mit Entwurf, aber ohne Phasen: Idee", () => {
    // Der Fall, den die Jahresplanung bis 11.09.2026 verschwieg — die Zeile sah
    // aus wie eine fertig geplante Stunde.
    expect(entwurfsStand({ stunde_node_id: "n-1", hat_phasen: false })).toBe("idee")
  })

  it("mit Phasen: Entwurf", () => {
    expect(entwurfsStand({ stunde_node_id: "n-1", hat_phasen: true })).toBe("entwurf")
  })

  it("`hat_phasen` fehlt ganz: Idee, nicht Entwurf", () => {
    // Ältere Antworten und andere Endpunkte liefern das Feld nicht. Dann lieber
    // „noch nichts drin" annehmen als Fertigstellung behaupten — ein falsches
    // „Idee" kostet einen Blick, ein falsches „fertig" eine Unterrichtsstunde.
    expect(entwurfsStand({ stunde_node_id: "n-1" })).toBe("idee")
  })

  it("verträgt null und leeres Objekt", () => {
    expect(entwurfsStand(null)).toBe("keiner")
    expect(entwurfsStand(undefined)).toBe("keiner")
    expect(entwurfsStand({})).toBe("keiner")
  })

  it("kennt die Nachbereitung nicht", () => {
    // Sie ist keine Stufe des Entwurfs, und es gibt bereits ein Abzeichen dafür.
    // Sie hier mitzuführen hieße, dieselbe Tatsache an zwei Stellen zu kennen.
    expect(entwurfsStand({ stunde_node_id: "n-1", hat_phasen: false, nachbereitet_at: "2026-09-01T08:00:00Z" }))
      .toBe("idee")
  })
})

describe("mitPhasenKennungen", () => {
  it("ergänzt eine fehlende Kennung", () => {
    const [phase] = mitPhasenKennungen([{ name: "Erarbeitung" }])
    expect(phase.id).toBeTruthy()
    expect(phase.name).toBe("Erarbeitung")
  })

  it("ergänzt auch, wenn der Server null schickt", () => {
    // ⚠️ Der Fall, an dem die frühere Fassung stillschweigend scheiterte:
    // `{ id: p.id ?? crypto.randomUUID(), ...p }` — der Spread stand *hinter* der
    // Zuweisung und überschrieb die eben erzeugte Kennung wieder mit null.
    // Der Server liefert genau das: `patch_lesson` speichert mit
    // `exclude_none=False`, eine Phase ohne Kennung wird als `"id": null` abgelegt.
    const [phase] = mitPhasenKennungen([{ id: null, name: "P" }])
    expect(phase.id).toBeTruthy()
    expect(phase.id).not.toBeNull()
  })

  it("ergänzt bei leerer Zeichenkette", () => {
    const [phase] = mitPhasenKennungen([{ id: "  ", name: "P" }])
    expect(phase.id.trim()).toBeTruthy()
  })

  it("lässt eine vorhandene Kennung unangetastet", () => {
    // Sie neu zu vergeben bräche `phasen_status` und übertragene Phasen.
    const [phase] = mitPhasenKennungen([{ id: "p1", name: "P" }])
    expect(phase.id).toBe("p1")
  })

  it("vergibt untereinander verschiedene Kennungen", () => {
    const phasen = mitPhasenKennungen([{ name: "A" }, { name: "B" }, { name: "C" }])
    expect(new Set(phasen.map((p) => p.id)).size).toBe(3)
  })

  it("ändert einen fertigen Stand beim zweiten Lauf nicht", () => {
    const einmal = mitPhasenKennungen([{ name: "A" }, { id: "p2", name: "B" }])
    const zweimal = mitPhasenKennungen(einmal)
    expect(zweimal.map((p) => p.id)).toEqual(einmal.map((p) => p.id))
  })

  it("erhält die übrigen Felder", () => {
    const [phase] = mitPhasenKennungen([
      { name: "P", dauer_min: 15, material: [{ typ: "node", node_id: "abc" }] },
    ])
    expect(phase.dauer_min).toBe(15)
    expect(phase.material).toEqual([{ typ: "node", node_id: "abc" }])
  })

  it("verträgt leere und fehlende Eingaben", () => {
    expect(mitPhasenKennungen([])).toEqual([])
    expect(mitPhasenKennungen(null)).toEqual([])
    expect(mitPhasenKennungen(undefined)).toEqual([])
  })
})
