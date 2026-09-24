/**
 * Persönlicher Ausfall in der Oberfläche (Paket 5, AP4).
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import {
    assistentFrage,
    ausfallWege,
    darfZurueckgenommenWerden,
    eintragFrage,
    zeileBrauchtEntscheidung,
    herkunftText,
    ruecknahmeWarnung,
} from "./ausfall.js"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const ZEILE = readFileSync(join(SRC, "lib/components/planner/PlannerRow.svelte"), "utf8")

describe("herkunftText", () => {
    it("unterscheidet die drei Quellen", () => {
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "stundenplan" }))
            .toContain("Stundenplan")
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "eigen" }))
            .toContain("selbst")
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "assistent" }))
            .toContain("Assistenten")
    })

    it("⚠️ prüft die Kategorie mit", () => {
        // `ausfall_herkunft` bleibt stehen, wenn eine Stunde die Kategorie über einen
        // Weg verlässt, der die Felder nicht mitführt — der Snapshot-Restore schreibt
        // aus einem JSON ohne diese Spalten. Ohne die Prüfung meldete die Zeile einen
        // Ausfall, den es nicht mehr gibt.
        expect(herkunftText({ kategorie: "unterricht", ausfall_herkunft: "eigen" }))
            .toBeNull()
    })

    it("schweigt bei unbekannter Herkunft", () => {
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: null })).toBeNull()
        expect(herkunftText({ kategorie: "ausfall", ausfall_herkunft: "irgendwas" }))
            .toBeNull()
    })
})

describe("darfZurueckgenommenWerden", () => {
    it("nur Eigenes", () => {
        expect(darfZurueckgenommenWerden(
            { kategorie: "ausfall", ausfall_herkunft: "eigen" })).toBe(true)
        // Ein Ausfall aus dem Stundenplan gehört dem Abgleich — ihn hier zu entfernen
        // überschriebe eine Auskunft der Schule, die ohnehin wiederkäme.
        expect(darfZurueckgenommenWerden(
            { kategorie: "ausfall", ausfall_herkunft: "stundenplan" })).toBe(false)
    })
})

describe("ruecknahmeWarnung", () => {
    it("⚠️ kündigt an, was sonst still geschähe", () => {
        // F4: Nach dem Schreiben ist einzeln von tagesweit nicht mehr unterscheidbar.
        const w = ruecknahmeWarnung("tag")
        expect(w).toContain("einzeln")
        expect(w).toContain("Stundenplan")
    })

    it("schweigt, wo es nichts anzukündigen gibt", () => {
        expect(ruecknahmeWarnung("gruppe")).toBeNull()
    })
})

describe("eintragFrage", () => {
    it("nennt die Reichweite beim Namen", () => {
        expect(eintragFrage("tag")).toContain("Alle Ihre Stunden dieses Tages")
        expect(eintragFrage("gruppe", "9C")).toContain("9C")
    })
})

describe("Zeile im Jahresplan (Quelltext-Wächter)", () => {
    it("zeigt die Herkunft an", () => {
        // Ohne sie sähen ein Stundenplan-Ausfall und ein selbst gesetzter gleich aus,
        // und die Lehrkraft wüsste nicht, ob sie ihn zurücknehmen kann.
        expect(ZEILE).toMatch(/\{#if herkunft\}/)
    })

    it("bietet beide Wege an, aber nie beide zugleich", () => {
        expect(ZEILE).toMatch(/\{#if eigenerAusfall\}/)
        expect(ZEILE).toContain("Ausfall zurücknehmen")
        expect(ZEILE).toContain("Ich falle aus")
    })
})

describe("Planungsseite: Auffrischen nach einer Server-Aktion", () => {
    const SEITE = readFileSync(
        join(SRC, "routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte"),
        "utf8",
    )

    it("⚠️ übernimmt die Slots des Servers, statt die lokalen zu behalten", () => {
        // Gemeldet von Jan (24.09.2026): Ein ganztägiger Ausfall erschien erst nach
        // manuellem Neuladen. Die Auffrischung behielt für bestehende Slots die lokale
        // Kopie — richtig auf dem PATCH-Pfad, falsch nach allem, was der Server von
        // sich aus ändert. Derselbe Fehler bestand beim Löschen einer Einheit
        // (`ON DELETE SET NULL` auf `ue_node_id`).
        const fn = SEITE.slice(SEITE.indexOf("async function refreshVomServer"))
        const rumpf = fn.slice(0, fn.indexOf("\n  }"))
        expect(rumpf).toContain("slots = refreshed.slots")
        expect(rumpf).not.toMatch(/slots\.find\(/)
    })

    it("beide Ausfall-Wege frischen auf", () => {
        // Ohne das bliebe die Zeile stehen, wie sie war — und die Lehrkraft hielte den
        // Eintrag für gescheitert.
        for (const fn of ["ausfallGanzerTag", "ausfallZurueck"]) {
            const block = SEITE.slice(SEITE.indexOf(`async function ${fn}`))
            expect(block.slice(0, block.indexOf("\n  }")), fn)
                .toContain("refreshVomServer()")
        }
    })
})

describe("ausfallWege", () => {
    it("⚠️ fragt nicht, wo es nichts zu entscheiden gibt", () => {
        // Eine leere Stunde fällt aus, und damit ist es gut. Danach zu fragen hieße,
        // nach Arbeit zu rufen, die niemand hat — und der Hinweis verlöre seine
        // Bedeutung für die Fälle, in denen es wirklich etwas zu tun gibt.
        expect(ausfallWege({ betroffen: 3, mit_inhalt: 0 })).toBeNull()
        expect(ausfallWege({})).toBeNull()
        expect(ausfallWege(null)).toBeNull()
    })

    it("bietet genau die drei Wege an", () => {
        const a = ausfallWege({ betroffen: 2, mit_inhalt: 2 })
        expect(a.wege.map((w) => w.id)).toEqual(["entfallen", "verschieben", "umplanen"])
        // Jeder trägt einen Hinweis — die Wörter allein sagen nicht, was folgt.
        expect(a.wege.every((w) => w.hinweis?.length > 10)).toBe(true)
    })

    it("zählt richtig", () => {
        expect(ausfallWege({ mit_inhalt: 1 }).satz).toContain("Eine")
        expect(ausfallWege({ mit_inhalt: 3 }).satz).toContain("3")
    })
})

describe("assistentFrage", () => {
    it("⚠️ trennt Verschieben von Umplanen", () => {
        // Zwei Absichten, zwei Sätze. In einen gelegt, träfe das Modell die
        // Entscheidung, die gerade die Lehrkraft getroffen hat.
        const v = assistentFrage("verschieben", "2026-11-10")
        const u = assistentFrage("umplanen", "2026-11-10")
        expect(v).toMatch(/verschieb/)
        // ⚠️ Nennt, was mitkommen soll: Am 24.09.2026 kam nur das Thema an.
        expect(v).toContain("Unterrichtseinheit")
        expect(v).toContain("Stundenentwurf")
        expect(u).toMatch(/kürzen|umverteilen/)
        expect(v).not.toBe(u)
    })

    it("nennt das Datum lesbar", () => {
        expect(assistentFrage("verschieben", "2026-11-03")).toContain("3.11.2026")
    })

    it("kommt ohne Datum zurecht", () => {
        expect(assistentFrage("umplanen", null)).toContain("diesem Tag")
    })
})

describe("zeileBrauchtEntscheidung", () => {
    const offen = {
        kategorie: "ausfall", anpassung_noetig: true, thema: "Titration",
    }

    it("⚠️ liest die Daten, nicht den Sitzungszustand", () => {
        // Jan, 24.09.2026: Der Hinweis stand über der Tabelle und verschwand beim
        // Neuladen — die offene Entscheidung wurde unsichtbar, obwohl sie offen blieb.
        expect(zeileBrauchtEntscheidung(offen)).toBe(true)
    })

    it("schweigt nach der Entscheidung", () => {
        // „Inhalte entfallen" räumt `anpassung_noetig` ab. Ohne diese Prüfung stünde der
        // Hinweis auch danach noch da.
        expect(zeileBrauchtEntscheidung({ ...offen, anpassung_noetig: false })).toBe(false)
    })

    it("schweigt an einer Stunde, die stattfindet", () => {
        expect(zeileBrauchtEntscheidung({ ...offen, kategorie: "unterricht" })).toBe(false)
    })

    it("⚠️ schweigt, wo nichts geplant war", () => {
        // Eine leere Stunde fällt aus, und damit ist es gut.
        expect(zeileBrauchtEntscheidung({
            kategorie: "ausfall", anpassung_noetig: true, thema: "   ",
        })).toBe(false)
    })

    it("erkennt Einheit und Entwurf als Inhalt", () => {
        for (const feld of ["ue_node_id", "stunde_node_id"]) {
            expect(zeileBrauchtEntscheidung({
                kategorie: "ausfall", anpassung_noetig: true, [feld]: "x",
            }), feld).toBe(true)
        }
    })
})

describe("Zeile: bearbeiten ohne Unterrichtseinheit", () => {
    const ZEILE2 = readFileSync(join(SRC, "lib/components/planner/PlannerRow.svelte"), "utf8")

    it("⚠️ hängt das Bearbeiten-Symbol nicht mehr an der Einheit", () => {
        // Es stand auf `slot.ue_node_id` — aus der Zeit, als ein Entwurf nur unter einer
        // Einheit entstehen konnte. Seit `POST /planning/slots/{id}/lesson` stimmt das
        // nicht mehr; am Ziel einer verschobenen Stunde fehlte das Symbol (Jan).
        expect(ZEILE2).toMatch(/\{#if onEditLesson && hatInhalt\}/)
        expect(ZEILE2).not.toMatch(/\{#if onEditLesson && slot\.ue_node_id\}/)
    })

    it("zeigt es nicht an leeren Zeilen", () => {
        const def = ZEILE2.slice(ZEILE2.indexOf("const hatInhalt"))
        expect(def.slice(0, def.indexOf("\n\n"))).toMatch(/thema \|\| ''\)\.trim\(\)/)
    })
})

describe("Planungsseite: der Hinweis steht an der Zeile", () => {
    const SEITE2 = readFileSync(
        join(SRC, "routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte"), "utf8")

    it("⚠️ kein Seiten-Banner mehr für dieselbe Frage", () => {
        // Zwei Orte für eine Frage waren als Todo notiert; Jans Rückmeldung hat
        // entschieden, welcher bleibt.
        expect(SEITE2).not.toContain("ausfallAngebot")
    })

    it("reicht den Weg an die Tabelle durch", () => {
        expect(SEITE2).toContain("onAusfallWeg={ausfallWegZeile}")
    })

    it("legt Entwürfe auch ohne Einheit an", () => {
        const fn = SEITE2.slice(SEITE2.indexOf("async function handleEditLesson"))
        const rumpf = fn.slice(0, fn.indexOf("\n  }"))
        expect(rumpf).toContain("createLessonForSlot")
        // ⚠️ **Ohne Kommentarzeilen prüfen.** Der erste Entwurf dieses Tests schlug an,
        // weil der Kommentar daneben die alte Zeile zitiert — ein Wächter, der auf die
        // Begründung anspringt statt auf den Code, meldet jede gute Dokumentation als
        // Fehler.
        const code = rumpf.split("\n").filter((z) => !z.trim().startsWith("//")).join("\n")
        expect(code).not.toMatch(/if \(!slot\?\.ue_node_id\) return/)
    })
})
