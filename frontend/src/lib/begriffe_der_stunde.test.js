/**
 * Begriffe der Stunde in der Kompetenzleiste (0.17, A1, Schritt 3).
 *
 * Die Logik steht in `begriffe_der_stunde.js`; was an den Komponenten hängt (welche Props es
 * gibt, dass nichts angelegt wird), prüfen die Quelltext-Tests unten — wie bei
 * `vokabel_chip.test.js`.
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { getContextNodes } from "./api.js"
import {
    BEGRIFF_TYPEN, SUCHGRENZE, aufteilen, begriffAusTreffer, bezugsfach, mitBegriff,
    ohneBegriff, ordneTreffer, suchparameter,
} from "./begriffe_der_stunde.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const quelle = (pfad) => readFileSync(join(SRC, pfad), "utf8")

const IK = { node_id: "ik-1", typ: "ik", code: "3.2.1(1)", titel: "Kompetenz", partiell: false }
const PK = { node_id: "pk-1", typ: "pk", code: "2.1", titel: "Prozess", partiell: false }
const BENZOL = { node_id: "b-1", typ: "concept", titel: "Benzol", partiell: false, content_type: "stoffsteckbrief" }

afterEach(() => vi.restoreAllMocks())

describe("Begriffe und Kompetenzen getrennt", () => {
    it("teilt gemischte refs in beide Gruppen, in gespeicherter Reihenfolge", () => {
        const { kompetenzen, begriffe } = aufteilen([IK, BENZOL, PK])
        expect(kompetenzen).toEqual([IK, PK])
        expect(begriffe).toEqual([BENZOL])
    })

    it("hält leere und fehlende refs aus", () => {
        expect(aufteilen(undefined)).toEqual({ kompetenzen: [], begriffe: [] })
    })

    it("einen Begriff dazu lässt die Kompetenzen stehen — und keinen doppelt", () => {
        const neu = mitBegriff([IK, PK], BENZOL)
        expect(neu).toEqual([IK, PK, BENZOL])
        expect(mitBegriff(neu, BENZOL)).toBe(neu)
    })

    it("einen Begriff entfernen lässt die Kompetenzen stehen", () => {
        expect(ohneBegriff([IK, BENZOL, PK], "b-1")).toEqual([IK, PK])
    })

    it("entfernt nur Begriffe — eine Kompetenz mit derselben Kennung bleibt", () => {
        const gleicheKennung = { ...IK, node_id: "b-1" }
        expect(ohneBegriff([gleicheKennung, BENZOL], "b-1")).toEqual([gleicheKennung])
    })

    it("der Eintrag aus einem Treffer trägt Typ, Titel und Bausteinart", () => {
        expect(begriffAusTreffer({ id: "b-1", title: "Benzol", content_type: "stoffsteckbrief", subject_id: 3 }))
            .toEqual(BENZOL)
    })
})

describe("Suche der Leiste", () => {
    it("sucht Begriffe des Fachs samt Bezugsfächern", () => {
        expect(suchparameter("Sub", 7)).toEqual({
            q: "Sub", content_type: BEGRIFF_TYPEN, status: "active", limit: SUCHGRENZE,
            subject_id: 7, mit_bezugsfaechern: true,
        })
    })

    it("ohne Fach ohne Fachfilter", () => {
        const params = suchparameter("Sub", null)
        expect(params).not.toHaveProperty("subject_id")
        expect(params).not.toHaveProperty("mit_bezugsfaechern")
    })

    it("die Parameter erreichen den Endpunkt", async () => {
        global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] })
        await getContextNodes(suchparameter("Sub", 7))
        const url = new URL(global.fetch.mock.calls[0][0], "http://x")
        expect(url.searchParams.get("subject_id")).toBe("7")
        expect(url.searchParams.get("mit_bezugsfaechern")).toBe("true")
        expect(url.searchParams.getAll("content_type")).toEqual(["begriff", "stoffsteckbrief"])
    })

    it("ordnet Treffer, die mit dem Gesuchten beginnen, zuerst — dann alphabetisch", () => {
        const treffer = [
            { title: "elektrophile Substitution" }, { title: "Substitution" },
            { title: "radikalische Substitution" }, { title: "Substanz" },
        ]
        expect(ordneTreffer(treffer, "sub").map((n) => n.title)).toEqual([
            "Substanz", "Substitution", "elektrophile Substitution", "radikalische Substitution",
        ])
    })

    it("nennt das Fach nur bei einem Treffer aus einem Bezugsfach", () => {
        const faecher = { 3: { name: "Chemie" }, 7: { name: "NwT" } }
        expect(bezugsfach({ subject_id: 3 }, 7, faecher)).toBe("Chemie")
        expect(bezugsfach({ subject_id: 7 }, 7, faecher)).toBeNull()
        expect(bezugsfach({ subject_id: 9 }, 7, faecher)).toBeNull()   // Fächer noch nicht geladen
    })
})

describe("Komponenten (Quelltext)", () => {
    const LEISTE = quelle("lib/components/planner/CompetenceBar.svelte")
    const AUSWAHL = quelle("lib/components/planner/BegriffSelector.svelte")

    it("Kompetenzen bearbeiten lässt die Begriffe stehen", () => {
        // IK- und PK-Auswahl ersetzen nur Einträge ihres eigenen Typs.
        expect(LEISTE).toContain("refs.filter(r => r.typ !== 'ik')")
        expect(LEISTE).toContain("refs.filter(r => r.typ !== 'pk')")
    })

    it("die Auswahl sucht über die gemeinsamen Parameter und legt nichts an", () => {
        expect(AUSWAHL).toContain("getContextNodes(suchparameter(q, subjectId))")
        expect(AUSWAHL).not.toContain("createContextNode")
    })

    it("die toten Vorschlags-Chips sind weg", () => {
        const seite = quelle("routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte")
        const phasen = quelle("lib/components/planner/PhaseTable.svelte")
        expect(LEISTE).not.toMatch(/suggestions\s*=|#each suggestions|onDismissSuggestion/)
        expect(seite).not.toMatch(/onSuggestCompetences|onDismissSuggestion|refs_dismissed/)
        expect(phasen).not.toContain("onSuggestCompetences")
    })
})
