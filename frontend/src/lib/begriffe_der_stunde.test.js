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
    BEGRIFF_TYPEN, SUCHGRENZE, aliaseText, aufteilen, begriffAnzeige, begriffAusTreffer,
    bezugsfach, getroffenesAlias, kurzdatum, mitBegriff, mitVerworfen, offeneVorschlaege, ohneAlias,
    ohneBegriff, ordneTreffer, refAusVorschlag, suchparameter, vorschlagFehlerText,
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

    it("zeigt die Aliase hinter dem Titel — ohne Aliase nur den Titel", () => {
        const se = { node_id: "b-2", typ: "concept", titel: "elektrophile Substitution",
                     aliase: ["σ-Komplex", "Arenium-Ion"] }
        expect(aliaseText(se)).toBe("σ-Komplex, Arenium-Ion")
        expect(begriffAnzeige(se)).toBe("elektrophile Substitution · σ-Komplex, Arenium-Ion")
        expect(aliaseText(BENZOL)).toBe("")
        expect(begriffAnzeige(BENZOL)).toBe("Benzol")
    })

    it("Kompetenzen ändern lässt die Aliase eines Begriffs stehen", () => {
        const se = { node_id: "b-2", typ: "concept", titel: "elektrophile Substitution", aliase: ["σ-Komplex"] }
        expect(mitBegriff([IK, se], BENZOL)).toEqual([IK, se, BENZOL])
        expect(ohneBegriff([IK, se, BENZOL], "b-1")[1].aliase).toEqual(["σ-Komplex"])
    })

    it("der Eintrag aus einem Treffer trägt Typ, Titel und Bausteinart", () => {
        expect(begriffAusTreffer({ id: "b-1", title: "Benzol", content_type: "stoffsteckbrief", subject_id: 3 }))
            .toEqual(BENZOL)
    })
})

describe("Aliase einzeln (0.18, Schritt 3)", () => {
    const SE = { node_id: "b-2", typ: "concept", titel: "elektrophile Substitution",
                 aliase: ["σ-Komplex", "Arenium-Ion"] }
    const TREFFER = { id: "b-2", title: "elektrophile Substitution", content_type: "begriff",
                      aliase: ["σ-Komplex", "Arenium-Ion"] }

    it("entfernt ein Alias, der Begriff und die anderen bleiben", () => {
        expect(ohneAlias([IK, SE], "b-2", "σ-Komplex")).toEqual([IK, { ...SE, aliase: ["Arenium-Ion"] }])
    })

    it("ohne letztes Alias bleibt der Begriff — ohne Schlüssel", () => {
        const nur = { ...SE, aliase: ["Arenium-Ion"] }
        const [ergebnis] = ohneAlias([nur], "b-2", "Arenium-Ion")
        expect(ergebnis).toEqual({ node_id: "b-2", typ: "concept", titel: "elektrophile Substitution" })
    })

    it("rührt Kompetenzen und andere Begriffe nicht an", () => {
        expect(ohneAlias([IK, BENZOL, SE], "b-1", "σ-Komplex")).toEqual([IK, BENZOL, SE])
    })

    it("erkennt das Alias, über das die Suche traf — nicht, wenn der Titel passt", () => {
        expect(getroffenesAlias(TREFFER, "σ-kom")).toBe("σ-Komplex")
        expect(getroffenesAlias(TREFFER, "ARENIUM")).toBe("Arenium-Ion")
        expect(getroffenesAlias(TREFFER, "Substitution")).toBeNull()
        expect(getroffenesAlias(TREFFER, "")).toBeNull()
    })

    it("der Eintrag aus einem Alias-Treffer trägt das Alias mit", () => {
        expect(begriffAusTreffer(TREFFER, "σ-Kom").aliase).toEqual(["σ-Komplex"])
        expect(begriffAusTreffer(TREFFER, "elektrophil")).not.toHaveProperty("aliase")
    })

    it("die Auswahl bietet ein × je Alias und gibt das Gesuchte weiter", () => {
        const auswahl = quelle("lib/components/planner/BegriffSelector.svelte")
        const leiste = quelle("lib/components/planner/CompetenceBar.svelte")
        expect(auswahl).toContain("onRemoveAlias(b.node_id, alias)")
        expect(auswahl).toContain("begriffAusTreffer(node, draft)")
        expect(leiste).toContain("onChange(ohneAlias(refs, nodeId, alias))")
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

    it("die toten Vorschlags-Chips aus 0.15 sind weg", () => {
        // `refs_dismissed` ist seit 0.18 wieder in Gebrauch — für die Vorschläge aus den
        // Phasentexten (Schritt 6), nicht für die alten Chips.
        const seite = quelle("routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte")
        const phasen = quelle("lib/components/planner/PhaseTable.svelte")
        expect(LEISTE).not.toMatch(/suggestions\s*=|#each suggestions|onDismissSuggestion/)
        expect(seite).not.toMatch(/onSuggestCompetences|onDismissSuggestion/)
        expect(phasen).not.toContain("onSuggestCompetences")
    })
})

describe("Entwurfsseite (Schritt 4)", () => {
    const SEITE = quelle("routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte")

    it("die Nachbereitung fragt nach Kompetenzen und Begriffen, Begriffe mit Symbol", () => {
        const schritt = SEITE.slice(SEITE.indexOf("reviewStep === 'refs'"))
        expect(schritt).toContain("Welche Kompetenzen und Begriffe wurden durch die offenen Phasen nicht behandelt?")
        expect(schritt).toContain("Markierte Einträge werden nicht")
        expect(schritt).toMatch(/ref\.typ === 'concept'[\s\S]*?<NodeTypeIcon/)
    })

    it("nennt die Unterrichtsgruppe im Kopf", () => {
        // Bei eingeklappter Sidebar war sonst nicht zu sehen, zu welcher Gruppe der Entwurf
        // gehört (Jan, 16.10.2026). Quelle wie in der Jahresübersicht.
        expect(SEITE).toContain("$myTeachingGroups.find(g => g.id === groupId)")
        const kopf = SEITE.slice(SEITE.indexOf("<!-- Breadcrumb -->"), SEITE.indexOf("Jahresübersicht</a>"))
        expect(kopf).toContain("{gruppe.name}")
    })
})

describe("Vorschläge aus den Phasentexten (0.18, Schritt 6)", () => {
    const VORSCHLAG = {
        aktuell: true,
        eintraege: [
            { node_id: "b-1", titel: "Benzol", content_type: "stoffsteckbrief", aliase: [], phase: "Einstieg", art: "eingeführt" },
            { node_id: "b-2", titel: "elektrophile Substitution", content_type: "begriff", aliase: ["σ-Komplex"] },
            { node_id: "b-3", titel: "Elektrophil", content_type: "begriff", aliase: [] },
        ],
        frueher: [{ node_id: "b-4", titel: "Aromaten", datum: "2026-10-05" }],
        ohne_knoten: [{ name: "Hückel-Regel" }],
        hinweis_frueher: "… kein Lernstand …",
    }

    it("offen ist, was weder eingetragen noch verworfen ist", () => {
        const o = offeneVorschlaege(VORSCHLAG, [IK, BENZOL], ["b-3"])
        expect(o.eintraege.map((e) => e.node_id)).toEqual(["b-2"])
        expect(o.frueher.map((f) => f.node_id)).toEqual(["b-4"])
        expect(o.ohne).toEqual([{ name: "Hückel-Regel" }])
        expect(offeneVorschlaege(null, [], [])).toEqual({ eintraege: [], frueher: [], ohne: [] })
    })

    it("ein übernommener Vorschlag wird ein Begriff samt Aliasen", () => {
        expect(refAusVorschlag(VORSCHLAG.eintraege[1])).toEqual({
            node_id: "b-2", typ: "concept", titel: "elektrophile Substitution", partiell: false,
            content_type: "begriff", aliase: ["σ-Komplex"],
        })
        expect(refAusVorschlag(VORSCHLAG.eintraege[0])).not.toHaveProperty("aliase")
        // Ein früherer Begriff (ohne Bausteinart) bekommt das Standardsymbol.
        expect(refAusVorschlag(VORSCHLAG.frueher[0]).content_type).toBe("begriff")
    })

    it("verwerfen ohne Doppel", () => {
        expect(mitVerworfen(["a"], "b")).toEqual(["a", "b"])
        expect(mitVerworfen(["a"], "a")).toEqual(["a"])
        expect(mitVerworfen(undefined, "a")).toEqual(["a"])
    })

    it("Datum kurz, Fehler als Satz", () => {
        expect(kurzdatum("2026-10-05")).toBe("5.10.")
        expect(kurzdatum(undefined)).toBe("")
        expect(vorschlagFehlerText("budget")).toMatch(/Budget/)
        expect(vorschlagFehlerText("irgendwas")).toMatch(/nicht möglich/)
        expect(vorschlagFehlerText(null)).toBeNull()
    })

    it("die Leiste bindet die Vorschläge ein, nie im Lesezustand", () => {
        const leiste = quelle("lib/components/planner/CompetenceBar.svelte")
        expect(leiste).toContain("{#if !readonly && (vorschlagMoeglich || vorschlag)}")
        expect(leiste).toContain("onUebernehmen={(ref) => onChange(mitBegriff(refs, ref))}")
    })

    it("die Seite speichert Verworfenes, gibt den Lesezustand weiter und speichert vor dem Vorschlag", () => {
        const seite = quelle("routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte")
        expect(seite).toContain("refs_dismissed: verworfen")
        expect(seite).toContain("readonly={nurLesen}")
        expect(seite).toMatch(/await doSave\(\)\s*\n\s*vorschlagLaedt = true/)
    })

    it("die Vorschlagszeile zeigt den Hinweis zu früheren Stunden und klappt Namen ohne Eintrag ein", () => {
        const zeile = quelle("lib/components/planner/BegriffVorschlag.svelte")
        expect(zeile).toContain("vorschlag?.hinweis_frueher")
        expect(zeile).toMatch(/<details[\s\S]*ohne Eintrag im Wissensspeicher/)
        expect(zeile).not.toMatch(/bekannt/i)
    })
})

