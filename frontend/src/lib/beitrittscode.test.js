import { describe, it, expect } from "vitest"
import {
    beitritteAbsteigend,
    beitritteGesamt,
    beitrittFehler,
    codeHinweis,
    codeLage,
    ruecknahmeFrage,
} from "./beitrittscode.js"

describe("codeLage", () => {
    it("unterscheidet abgelaufen von gar nicht vorhanden", () => {
        // ⚠️ Zwei verschiedene Handlungen: erneuern oder erstmals ausgeben. Wer beides
        // gleich benennt, lässt die Lehrkraft rätseln, warum niemand beitreten kann.
        expect(codeLage(null)).toBe("keiner")
        expect(codeLage({ code: null })).toBe("keiner")
        expect(codeLage({ code: "ABCD-EFGH", gueltig: false })).toBe("abgelaufen")
        expect(codeLage({ code: "ABCD-EFGH", gueltig: true })).toBe("gueltig")
    })

    it("gibt je Lage einen eigenen Hinweis", () => {
        const saetze = new Set([
            codeHinweis(null),
            codeHinweis({ code: "A", gueltig: false }),
            codeHinweis({ code: "A", gueltig: true, gueltig_bis: "2026-09-26T10:00:00Z" }),
        ])
        expect(saetze.size).toBe(3)
    })
})

describe("ruecknahmeFrage", () => {
    it("nennt die Zahl und die Folge", () => {
        // ⚠️ Die Folge gehört in den Satz: Ohne sie wirkt die Rücknahme wie Aufräumen,
        // und die Lehrkraft steht danach vor einer Klasse, die nicht mehr hineinkommt.
        const frage = ruecknahmeFrage(24)
        expect(frage).toContain("24 Beitritte")
        expect(frage).toContain("ungültig")
        expect(frage).toContain("erneut beitreten")
    })

    it("nennt den Tag, wenn nur einer zurückgenommen wird", () => {
        expect(ruecknahmeFrage(3, "2026-09-24")).toContain("24.09.2026")
    })

    it("formuliert die Einzahl richtig", () => {
        expect(ruecknahmeFrage(1)).toContain("1 Beitritt wird")
    })
})

describe("beitritte", () => {
    const antwort = {
        beitritte: [
            { tag: "2026-09-23", anzahl: 24 },
            { tag: "2026-09-24", anzahl: 3 },
        ],
    }

    it("zeigt den jüngsten Tag zuerst", () => {
        // Der jüngste ist der verdächtige — dort sucht man den Fehlbeitritt.
        expect(beitritteAbsteigend(antwort)[0].tag).toBe("2026-09-24")
    })

    it("zählt zusammen", () => {
        expect(beitritteGesamt(antwort)).toBe(27)
        expect(beitritteGesamt(null)).toBe(0)
    })
})

describe("beitrittFehler", () => {
    it("erklärt den abgelaufenen Code mit einer Handlung", () => {
        expect(beitrittFehler("Dieser Code ist abgelaufen.")).toContain("neuen")
    })

    it("verrät bei einem unbekannten Code nichts über fremde Gruppen", () => {
        const satz = beitrittFehler("Dieser Code gilt nicht.")
        expect(satz.toLowerCase()).not.toContain("gruppe")
    })
})
