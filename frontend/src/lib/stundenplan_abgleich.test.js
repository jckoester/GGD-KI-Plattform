import { describe, it, expect } from "vitest"
import {
    abgleichZusammenfassung,
    anlegbareGruppen,
    diagnose,
    diagnoseHatInhalt,
    fehlendesRaster,
    herkunftDerMitglieder,
    rasterJeGruppe,
    OHNE_GRUPPE,
    OHNE_SLOT,
    ZUR_GRUPPE,
    ZU_ANDERER,
} from "./stundenplan_abgleich.js"

const ohneSlot = (n) =>
    Array.from({ length: n }, (_, i) => ({
        datum: "2026-09-14", stunde: i + 1, grund: OHNE_SLOT,
        beschreibung: "Stundenplan kennt Unterricht, die Jahresplanung hat dort keinen Slot.",
    }))

describe("fehlendesRaster", () => {
    it("erkennt die leere Jahresplanung", () => {
        const meldung = fehlendesRaster({ geaendert: 0, konflikte: ohneSlot(48) })
        expect(meldung).toMatch(/keine Stunden angelegt/)
        expect(meldung).toMatch(/Aus Stundenplan übernehmen/)
    })

    it("schweigt, wenn es nichts zu melden gibt", () => {
        expect(fehlendesRaster({ geaendert: 0, konflikte: [] })).toBeNull()
        expect(fehlendesRaster({ geaendert: 3, konflikte: [] })).toBeNull()
        expect(fehlendesRaster(null)).toBeNull()
        expect(fehlendesRaster({})).toBeNull()
    })

    it("verdeckt keine echten Befunde", () => {
        // Ein gemischtes Ergebnis ist kein „leere Planung"-Fall: Dort stecken Hinweise,
        // die jemand lesen soll — etwa eine festgehaltene Stunde, die der Abgleich nicht
        // anfassen durfte.
        const gemischt = [...ohneSlot(2), { grund: "pinned", beschreibung: "…" }]
        expect(fehlendesRaster({ geaendert: 0, konflikte: gemischt })).toBeNull()
    })

    it("schweigt, sobald etwas geändert wurde", () => {
        // Dann hat der Abgleich gearbeitet; die übrigen „kein Slot"-Hinweise betreffen
        // einzelne Stunden, nicht die ganze Gruppe.
        expect(fehlendesRaster({ geaendert: 1, konflikte: ohneSlot(5) })).toBeNull()
    })

    it("schweigt bei erkannten Verlegungen", () => {
        // Eine Verlegung setzt voraus, dass es Slots gibt — dann ist die Planung nicht leer.
        expect(
            fehlendesRaster({
                geaendert: 0,
                konflikte: ohneSlot(3),
                verlegungen: [{ von_datum: "2026-09-14", nach_datum: "2026-09-15" }],
            }),
        ).toBeNull()
    })
})

describe("rasterJeGruppe", () => {
    const muster = (group_id, gruppe, weekday, sicher = true) => ({
        group_id, gruppe, weekday, start_period: 1, periods: 1,
        rhythmus: "woechentlich", sicher,
    })

    it("bündelt die flache Liste nach Gruppen", () => {
        const r = rasterJeGruppe({
            patterns: [
                muster(7, "Mathe 8a", 0),
                muster(7, "Mathe 8a", 2),
                muster(9, "Chemie KS", 1),
            ],
        })
        expect(r.map((g) => g.group_id)).toEqual([9, 7])  // alphabetisch nach Gruppenname
        expect(r.find((g) => g.group_id === 7).zeilen).toHaveLength(2)
    })

    it("lässt Zeilen ohne Gruppe weg", () => {
        // Lerngruppen aus dem Stundenplan, die es auf der Plattform nicht gibt —
        // dorthin lässt sich nichts schreiben.
        const r = rasterJeGruppe({
            patterns: [muster(null, "NwT 9a/9c", 0), muster(7, "Mathe 8a", 0)],
        })
        expect(r).toHaveLength(1)
        expect(r[0].group_id).toBe(7)
    })

    it("zählt die unsicheren Zeilen je Gruppe", () => {
        const r = rasterJeGruppe({
            patterns: [muster(7, "Mathe 8a", 0), muster(7, "Mathe 8a", 2, false)],
        })
        expect(r[0].unsicher).toBe(1)
    })

    it("verträgt eine leere Antwort", () => {
        expect(rasterJeGruppe(null)).toEqual([])
        expect(rasterJeGruppe({})).toEqual([])
        expect(rasterJeGruppe({ patterns: [] })).toEqual([])
    })
})


describe("diagnose", () => {
    // Nachgebaut aus der Produktionsantwort vom 14.09.2026: ein Kürzel, mehrere
    // Lerngruppen, eine davon ohne Gruppe.
    const ANTWORT = {
        kuerzel: "KS",
        wochen: ["2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"],
        patterns: [
            { gruppe: "CH 9D", subject_slug: "chemie", klassen: ["9D"], group_id: 49, weekday: 0 },
            { gruppe: "CH 9D", subject_slug: "chemie", klassen: ["9D"], group_id: 49, weekday: 2 },
            { gruppe: "M 9C", subject_slug: "mathematik", klassen: ["9C"], group_id: 56, weekday: 1 },
            { gruppe: "CH2_11", subject_slug: "chemie", klassen: ["11"], group_id: null, weekday: 3 },
        ],
        fehlende_gruppen: [{ name: "chemie 11 (Leistungskurs)", klassen: ["11"] }],
        unbekannte_faecher: [{ code: "SL", stunden: 2, klassen: ["SL"] }],
        hinweise: ["Nicht als Unterricht gewertet: PRÄS."],
    }

    it("führt jede Lerngruppe einmal, nicht jeden Termin", () => {
        const d = diagnose(ANTWORT, 49)
        expect(d.lerngruppen.map((l) => l.label)).toEqual(["CH 9D", "M 9C", "CH2_11"])
    })

    it("unterscheidet die drei Zuordnungslagen", () => {
        const d = diagnose(ANTWORT, 49)
        const nach = Object.fromEntries(d.lerngruppen.map((l) => [l.label, l.status]))
        expect(nach).toEqual({
            "CH 9D": ZUR_GRUPPE,
            "M 9C": ZU_ANDERER,
            CH2_11: OHNE_GRUPPE,
        })
    })

    it("reicht Kürzel, Wochenzahl und die übrigen Meldungen durch", () => {
        const d = diagnose(ANTWORT, 49)
        expect(d.kuerzel).toBe("KS")
        expect(d.wochen).toBe(4)
        expect(d.fehlend).toEqual([{ name: "chemie 11 (Leistungskurs)", klassen: ["11"] }])
        expect(d.unbekannt).toEqual([{ code: "SL", stunden: 2, klassen: ["SL"] }])
        expect(d.hinweise).toEqual(["Nicht als Unterricht gewertet: PRÄS."])
    })

    it("überlebt eine leere Antwort", () => {
        const d = diagnose(null, 1)
        expect(d.lerngruppen).toEqual([])
        expect(d.wochen).toBe(0)
    })

    it("trägt die Mehrdeutigkeitsmeldung der Zuordnung", () => {
        // Seit dem 15.09.2026 meldet der Abgleich, wenn er nicht entscheiden konnte —
        // das ist im Fehlschlag die wichtigste Auskunft überhaupt.
        const d = diagnose(
            { ...ANTWORT, hinweise: ["chemie 11: keine eindeutige Zuordnung — infrage kommen „Chemie 11“."] },
            49,
        )
        expect(d.hinweise[0]).toMatch(/keine eindeutige Zuordnung/)
    })
})

describe("diagnoseHatInhalt", () => {
    it("ist falsch, wenn nichts zu sagen ist", () => {
        expect(diagnoseHatInhalt(diagnose({ kuerzel: "KS" }, 1))).toBe(false)
        expect(diagnoseHatInhalt(null)).toBe(false)
    })

    it("ist wahr, sobald es einen einzigen Hinweis gibt", () => {
        // Der Fall „kein Kürzel im Profil": Der Endpunkt liefert nur einen Hinweis und
        // sonst nichts — und genau der erklärt den Fehlschlag.
        const d = diagnose({ hinweise: ["Im Profil ist kein Kürzel eingetragen."] }, 1)
        expect(diagnoseHatInhalt(d)).toBe(true)
    })
})

// ── Zusammenfassung und Einrichtungsfall nach AP4/AP5 (22.09.2026) ───────────

describe("abgleichZusammenfassung", () => {
    it("nennt angelegte Stunden eigens", () => {
        // `geaendert` zählt beides — die Zahl allein sagt nicht mehr, was geschah.
        const text = abgleichZusammenfassung({
            geaendert: 5,
            angelegte: [{ datum: "2026-03-02" }, { datum: "2026-03-03" }],
        });
        expect(text).toContain("3 Stunden geändert");
        expect(text).toContain("2 Stunden angelegt");
    });

    it("ohne Anlagen bleibt es bei der alten Form", () => {
        expect(abgleichZusammenfassung({ geaendert: 1 })).toBe("1 Stunde geändert");
    });
});

describe("fehlendesRaster nach AP4", () => {
    it("schweigt, wenn Termine angelegt wurden", () => {
        // Dann hat die Gruppe eine Planung — es ist nicht der Einrichtungsfall.
        const ergebnis = {
            geaendert: 0,
            konflikte: [{ grund: OHNE_SLOT }],
            angelegte: [{ datum: "2026-03-02" }],
        };
        expect(fehlendesRaster(ergebnis)).toBeNull();
    });

    it("greift weiterhin, wenn die Gruppe gar keine Planung hat", () => {
        const ergebnis = { geaendert: 0, konflikte: [{ grund: OHNE_SLOT }], angelegte: [] };
        expect(fehlendesRaster(ergebnis)).toContain("noch keine Stunden angelegt");
    });
});

// ── AP3: Woher kämen die Mitglieder? ─────────────────────────────────────────

describe("herkunftDerMitglieder", () => {
    it("nennt die Klasse, aus der geerbt wird", () => {
        const satz = herkunftDerMitglieder({
            erbt_aus: ["9d"],
            stammt_aus: ["9d"],
            klassen_ohne_treffer: [],
        })
        expect(satz).toBe("Mitglieder aus 9d")
    })

    it("erbt bei mehreren Klassen nicht, sondern verweist auf den Code", () => {
        // ⚠️ **Der Befund von Jan (23.09.2026).** Eine Gruppe über 10a/10b/10c ist eine
        // **Auswahl** aus diesen Klassen — sonst würde je Klasse unterrichtet. Alle drei
        // hineinzuschreiben gäbe Schüler:innen Zugang zu einer Gruppe, in der sie nicht
        // sind. Versprich hier „Mitglieder aus 10a, 10b und 10c", und der Fehler ist
        // schon passiert, bevor jemand ihn bemerkt.
        const satz = herkunftDerMitglieder({
            mehrklassig: true,
            erbt_aus: [],
            stammt_aus: ["10a", "10b", "10c"],
            klassen_ohne_treffer: [],
        })
        expect(satz).toContain("Teilgruppe")
        expect(satz).toContain("Code")
        expect(satz).not.toContain("Mitglieder aus")
    })

    it("verweist in der Kursstufe auf den Code", () => {
        // Dort heißt die „Klasse" 11 und meint einen ganzen Jahrgang — daraus wird
        // bewusst nicht geerbt.
        const satz = herkunftDerMitglieder({ kursstufe: true, erbt_aus: [] })
        expect(satz).toContain("Code")
        expect(satz).toContain("Kursstufe")
    })

    it("sagt, wenn eine genannte Klasse auf der Plattform fehlt", () => {
        const satz = herkunftDerMitglieder({
            erbt_aus: ["9a"],
            klassen_ohne_treffer: ["9b"],
        })
        expect(satz).toContain("9a")
        expect(satz).toContain("9b")
        expect(satz).toContain("gibt es hier noch nicht")
    })

    it("verspricht nichts, wenn gar keine Klasse passt", () => {
        // ⚠️ Der schlimmste Fall für die Lehrkraft: Sie legt an und die Gruppe bleibt
        // leer. Ohne diesen Satz stünde sie ohne Erklärung da.
        const satz = herkunftDerMitglieder({ erbt_aus: [], klassen_ohne_treffer: [] })
        expect(satz).toContain("Code")
        expect(satz).not.toContain("Mitglieder aus")
    })
})

describe("anlegbareGruppen", () => {
    it("übernimmt Schlüssel und Fach für die Anlage-Anfrage", () => {
        const [g] = anlegbareGruppen({
            fehlende_gruppen: [{
                gruppe: "CH 9D", name: "Chemie 9D", subject_id: 7,
                subject_slug: "chemie", klassen: ["9D"],
                erbt_aus: ["9D"], klassen_ohne_treffer: [], kursstufe: false,
            }],
        })
        expect(g.gruppe).toBe("CH 9D")
        expect(g.subjectId).toBe(7)
        expect(g.erbt).toBe(true)
    })

    it("ist leer, wenn nichts fehlt", () => {
        expect(anlegbareGruppen({ fehlende_gruppen: [] })).toEqual([])
        expect(anlegbareGruppen(null)).toEqual([])
    })
})
