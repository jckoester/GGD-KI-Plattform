/**
 * „Unterricht" ist eine eigene Seite (Paket 7, AP6).
 *
 * Kürzel, Abgleich und Unterrichtsgruppen saßen im **Profil**. Sie gehören nicht dorthin:
 * Man stellt sie in der Regel zu Schuljahresbeginn einmal ein, und mit dem Benutzerprofil
 * haben sie nichts zu tun (Jan, 25.09.2026).
 *
 * ⚠️ **Wächter über einen Umzug, nicht über Logik.** Ein Umzug hinterlässt zwei Sorten
 * Schaden, die niemandem auffallen: ein Verweis, der weiterhin auf die alte Adresse zeigt
 * (und dank Weiterleitung *funktioniert*, nur einen Umweg nimmt), und eine Bedienstelle,
 * die es plötzlich zweimal gibt.
 */
import { describe, it, expect } from "vitest"
import { readFileSync, existsSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const lies = (pfad) => readFileSync(join(SRC, pfad), "utf8")

describe("Die Seite Unterricht", () => {
    it("liegt unter /teaching und trägt Kürzel, Abgleich und Gruppen", () => {
        const seite = lies("routes/(app)/teaching/+page.svelte")
        expect(seite).toContain("webuntis-kuerzel")
        expect(seite).toContain("TimetableSyncButton")
        expect(seite).toContain("Meine Unterrichtsgruppen")
    })

    it("die alte Adresse leitet weiter, statt ins Leere zu laufen", () => {
        // Lesezeichen und ältere Links: Die Seite lag ein halbes Jahr unter
        // `/profile/teaching-groups`, und die Nutzer-Doku nannte sie so.
        const alt = lies("routes/(app)/profile/teaching-groups/+page.js")
        expect(alt).toContain("redirect(")
        expect(alt).toContain("/teaching")
        expect(existsSync(join(SRC, "routes/(app)/profile/teaching-groups/+page.svelte")))
            .toBe(false)
    })

    it("⚠️ kein Verweis zeigt mehr auf die alte Adresse", () => {
        // Sie funktionierte auch dann — über die Weiterleitung. Genau deshalb fiele es
        // nicht auf, und der Umweg bliebe für immer stehen.
        for (const pfad of [
            "lib/components/TagesKachel.svelte",
            "lib/components/GruppenKachel.svelte",
            "routes/(app)/profile/+page.svelte",
            "routes/(app)/subjects/[slug]/groups/[id]/+page.svelte",
        ]) {
            expect(lies(pfad), pfad).not.toContain("/profile/teaching-groups")
        }
    })

    it("⚠️ steht im Nutzermenü, nicht nur im Profil", () => {
        // Jan, 25.09.2026: „im Benutzermenü kam keine neue Seite Unterricht dazu." Eine
        // Seite, die nur über einen Verweis auf einer anderen Seite erreichbar ist, wird
        // dort gesucht, wo man Seiten sucht — und nicht gefunden.
        const menue = lies("lib/components/UserMenu.svelte")
        expect(menue).toContain('href="/teaching"')
    })

    it("das Profil trägt das Kürzel nicht mehr", () => {
        // Zwei Eingabefelder für dieselbe Einstellung wären schlimmer als ein Umzug.
        expect(lies("routes/(app)/profile/+page.svelte")).not.toContain("webuntis-kuerzel")
    })
})

describe("Die Kachelwahl steht im Profil", () => {
    it("dort ist sie bedienbar", () => {
        const profil = lies("routes/(app)/profile/+page.svelte")
        expect(profil).toContain("schalteKachel(")
        expect(profil).toContain("Kacheln der Startseite")
    })

    it("⚠️ auf der Startseite gibt es sie kein zweites Mal", () => {
        // Sie stand dort mit guter Begründung („wer eine Kachel weghaben will, denkt das
        // beim Ansehen"). Jan hat sie am 25.09.2026 ins Profil geholt; der **Weg** bleibt
        // als Verweis, die Bedienstelle nicht.
        const welcome = lies("routes/(app)/welcome/+page.svelte")
        expect(welcome).not.toContain("schalteKachel(")
        expect(welcome).toContain("Kacheln wählen")
    })
})

describe("Gespeichert wird quittiert", () => {
    const profil = lies("routes/(app)/profile/+page.svelte")

    it("⚠️ an jedem Feld, nicht als Seitenbanner", () => {
        // Bei sechs Einstellungen untereinander sagt ein Banner nicht, welche gemeint
        // ist. Seit dem Wegfall des „Speichern"-Knopfes (21.09.2026) meldete die Seite
        // gar nichts mehr.
        const stellen = profil.match(/quittung === "/g) ?? []
        expect(stellen.length).toBeGreaterThanOrEqual(6)
    })

    it("auch für die Wege, die nicht über `updatePreference` laufen", () => {
        // Darstellungsmodus, Darstellungsstufe und Kacheln schreiben über eigene Stores.
        // Ohne diese drei wäre die Rückmeldung genau dort still, wo man sie am ehesten
        // sucht.
        for (const key of ["theme", "ui_stufe", "startkacheln"]) {
            expect(profil, key).toContain(`quittiere('${key}')`)
        }
    })
})
