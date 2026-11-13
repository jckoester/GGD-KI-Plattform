// @vitest-environment jsdom
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { beforeEach, describe, expect, it } from "vitest"
import {
  ANHAENGBARE_ARTEN, mentionEintraege, mitProdukt, produktFuerNeuenChat, produkteUebernehmen,
} from "./produkt_im_chat.js"

const B = (id) => ({ node_id: id, title: `Baustein ${id}` })
const P = (id) => ({ artifact_id: id, kind: "document", title: `Produkt ${id}` })

describe("@-Liste mit zwei Gruppen", () => {
  it("Bausteine zuerst, Produkte darunter mit eigener Überschrift", () => {
    const liste = mentionEintraege([B("1"), B("2")], [P("a")])
    expect(liste.map((e) => [e.art, e.gruppe])).toEqual([
      ["baustein", "Bibliothek"], ["baustein", null], ["produkt", "Aus deiner Werkstatt"],
    ])
  })

  it("ohne Produkte keine Überschrift über den Bausteinen", () => {
    expect(mentionEintraege([B("1")], []).map((e) => e.gruppe)).toEqual([null])
  })

  it("nur Produkte: eine Liste, die die Tastatur trotzdem durchläuft", () => {
    expect(mentionEintraege([], [P("a"), P("b")]).map((e) => e.schluessel)).toEqual(["p:a", "p:b"])
  })

  it("verträgt null", () => {
    expect(mentionEintraege(null, null)).toEqual([])
  })
})

describe("Anhänge", () => {
  it("ein Produkt nur einmal", () => {
    const einmal = mitProdukt([], P("a"))
    expect(mitProdukt(einmal, P("a"))).toBe(einmal)
    expect(mitProdukt(einmal, P("b"))).toHaveLength(2)
  })

  it("dieselben Arten wie im Backend (`im_chat.ANHAENGBAR`)", () => {
    const backend = readFileSync(
      join(import.meta.dirname, "..", "..", "..", "backend", "app", "artifacts", "im_chat.py"), "utf8")
    const block = backend.slice(backend.indexOf("ANHAENGBAR:"), backend.indexOf("}", backend.indexOf("ANHAENGBAR:")))
    const arten = [...block.matchAll(/^\s+"(\w+)":/gm)].map((m) => m[1])
    expect(new Set(arten)).toEqual(ANHAENGBARE_ARTEN)
  })
})

describe("Übergabe aus der Werkstatt", () => {
  beforeEach(() => sessionStorage.clear())

  it("einmal abholbar", () => {
    produktFuerNeuenChat(P("a"))
    expect(produkteUebernehmen()).toEqual([{ artifact_id: "a", kind: "document", title: "Produkt a" }])
    expect(produkteUebernehmen()).toEqual([])
  })

  it("Kaputtes ergibt eine leere Liste", () => {
    sessionStorage.setItem("produkt-uebergabe", "{kaputt")
    expect(produkteUebernehmen()).toEqual([])
  })
})

describe("Chat", () => {
  const chat = readFileSync(join(import.meta.dirname, "..", "routes", "(app)", "chat", "+page.svelte"), "utf8")

  it("schickt die Produkte mit der ersten Nachricht", () => {
    expect(chat).toContain("produktIds: conversationId ? [] : pendingProdukte.map((p) => p.artifact_id)")
  })

  it("bietet in der Vorschau keine Produkte an", () => {
    expect(chat).toContain("inVorschau ? [] : getAnhaengbareProdukte(q, 5)")
    expect(chat).toContain("pendingProdukte = inVorschau ? [] : produkteUebernehmen()")
  })
})
