/**
 * Die drei Lagen, in denen kein Curriculum-Kapitel zur Auswahl steht.
 *
 * ⚠️ Bis zum 24.09.2026 sahen sie alle gleich aus — eine leere Liste mit dem Satz „Kein
 * Curriculum für diese Gruppe gefunden". Nur in einem der drei Fälle stimmte er.
 */
import { describe, it, expect } from "vitest"
import { curriculumLage } from "./curriculumlage.js"

const MIT_KAPITEL = { curricula: [{ kapitel: [{ id: "k1" }] }] }

describe("curriculumLage", () => {
    it("schweigt, wenn es etwas auszuwählen gibt", () => {
        expect(curriculumLage(MIT_KAPITEL)).toBeNull()
    })

    it("⚠️ nennt das fehlende Fach als das, was es ist", () => {
        const lage = curriculumLage({ curricula: [], fach_fehlt: true, grade_unbekannt: true })
        expect(lage.art).toBe("fach_fehlt")
        expect(lage.text).toContain("kein Fach")
        // Nicht nur das Problem — auch der Weg.
        expect(lage.tun).toContain("Klasse und Fach")
    })

    it("⚠️ unterscheidet die unbekannte Stufe vom fehlenden Curriculum", () => {
        const ohneStufe = curriculumLage({ curricula: [], grade_unbekannt: true })
        const ohneCurriculum = curriculumLage({ curricula: [], grade_unbekannt: false })
        expect(ohneStufe.art).toBe("stufe_unbekannt")
        expect(ohneCurriculum.art).toBe("kein_curriculum")
        expect(ohneStufe.text).not.toBe(ohneCurriculum.text)
    })

    it("⚠️ verspricht nicht mehr, alle Curricula des Fachs zu zeigen", () => {
        // Genau das stand früher da — und es war die Beschreibung eines Fehlers:
        // Einem Abi-28-Kurs wurde „CH Kl. 8" angeboten.
        const lage = curriculumLage({ curricula: [], grade_unbekannt: true })
        expect(`${lage.text} ${lage.tun}`).not.toMatch(/alle Curricula/i)
    })

    it("hält ein Curriculum ohne Kapitel nicht für eine Auswahl", () => {
        // Eine Auswahlliste mit null Einträgen ist keine Auswahl.
        expect(curriculumLage({ curricula: [{ kapitel: [] }] })?.art).toBe("kein_curriculum")
    })

    it("kommt mit einer leeren Antwort zurecht", () => {
        expect(curriculumLage({})?.art).toBe("kein_curriculum")
        expect(curriculumLage(null)?.art).toBe("kein_curriculum")
    })
})
