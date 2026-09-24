/**
 * Wächter für die Zeile der Tageskachel — am Quelltext, weil das Projekt keine
 * Svelte-Komponententests hat.
 *
 * ⚠️ **Dieser Wächter hat schon einmal versagt, und zwar lehrreich.** Er prüfte
 * `href={zumEntwurf}` und war zufrieden — ohne je zu fragen, ob `zumEntwurf` einen Wert
 * annimmt. Tat es nicht: `stunde_node_id` fehlte in der API-Antwort, der Titel rendelte
 * als reiner Text, der Wächter blieb grün.
 *
 * Die Lehre: **Ein Quelltext-Wächter kann nur bezeugen, dass etwas dasteht, nie dass es
 * wirkt.** Für das Wirken sind die Logiktests in `mein_tag.test.js` zuständig (dort geht
 * `titelAktion` den ganzen Zustandsraum ab) und der Integrationstest
 * `test_mein_tag_liefert_die_id_des_entwurfs`, der die Id über die echte Schnittstelle
 * holt. Hier bleibt nur, was sich **nirgends sonst** ausdrücken lässt: dass das Markup
 * die Werte überhaupt verwendet.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const KACHEL = readFileSync(join(SRC, "lib/components/TagesKachel.svelte"), "utf8")

describe("Zeile der Tageskachel", () => {
    it("zeigt das Fach-Icon am Zeilenanfang", () => {
        expect(KACHEL).toContain("<SubjectIcon")
        expect(KACHEL).toMatch(/name=\{s\.subject_icon\}/)
    })

    it("färbt es in der Fachfarbe", () => {
        // ⚠️ Ohne `color` fällt das Icon auf die Standardfarbe zurück — es sähe richtig
        // aus und wäre nutzlos: Die Farbe ist der Grund, warum man den Tag überfliegen
        // kann, ohne jeden Gruppennamen zu lesen. Das steht nur im Markup.
        expect(KACHEL).toMatch(/color=\{s\.subject_color\}/)
    })

    it("\u26a0\ufe0f rendert den Titel als `<a>`, nicht als Schaltfl\u00e4che", () => {
        // **Das ist kein Stil, sondern Sichtbarkeit.** Die Zeile steht in einem
        // `truncate`-Container; `text-overflow: ellipsis` k\u00fcrzt Text, aber keinen
        // Inline-Block. Ein `<button>` ist ein atomarer Kasten \u2014 passt er nicht, bleibt
        // vom Titel nur das \u201e\u2026". Genau so ist er am 24.09.2026 verschwunden.
        const zeile = KACHEL.slice(KACHEL.indexOf("{@const aktion"))
        expect(zeile).toMatch(/<a\s+href=\{aktion\.ziel\}/)
        expect(zeile.slice(0, zeile.indexOf("</a>"))).not.toContain("<button")
    })

    it("meldet, wenn das Anlegen scheitert", () => {
        // Ein Klick, der nichts tut und nichts sagt, ist die schlechteste Rückmeldung.
        expect(KACHEL).toMatch(/fehler = e\.message/)
        expect(KACHEL).toMatch(/<ErrorBanner message=\{fehler\}/)
    })

    it("macht aus dem Einheiten-Hinweis einen Weg, keinen Text", () => {
        expect(KACHEL).toMatch(/\{#if hinweis\?\.ziel\}/)
        expect(KACHEL).toMatch(/href=\{hinweis\.ziel\}/)
    })
})
