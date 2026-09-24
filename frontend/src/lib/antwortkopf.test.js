/**
 * Der Antwortkopf des Frontends muss klein bleiben.
 *
 * ⚠️ **Was dieser Test kann und was nicht.** Er misst den Kopf nicht — dafür bräuchte es
 * einen Build und einen laufenden Server. Er hält fest, **dass die Regel dasteht**, die
 * ihn klein hält, und **warum** sie dasteht. Gemessen wurde am 24.09.2026 von Hand:
 *
 * | Route | Vorgabe (`js` + `css`) | nur CSS |
 * |---|---|---|
 * | `/` | 2 460 B | 273 B |
 * | `/chat` | 7 041 B | 366 B |
 * | `/knowledge/curriculum/…` | 6 601 B | 468 B |
 *
 * nginx liest den Antwortkopf in **einen** Puffer (Vorgabe: eine Speicherseite, 4 KB).
 * Darüber: `upstream sent too big header` und **502** beim Neuladen jeder tiefen URL —
 * genau der Betatest-Befund vom 23.09.2026.
 */
import { describe, it, expect } from "vitest"
import { readFileSync, existsSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const SRC = dirname(dirname(fileURLToPath(import.meta.url)))
const HOOK = join(SRC, "hooks.server.js")
const NGINX = join(dirname(dirname(SRC)), "infra/nginx.conf")

describe("Vorlade-Hinweise", () => {
    it("⚠️ die Regel existiert", () => {
        // Ohne sie stehen 98 `modulepreload`-Einträge im `Link`-Kopf.
        expect(existsSync(HOOK), "hooks.server.js fehlt").toBe(true)
    })

    it("⚠️ es wird nur CSS vorgeladen", () => {
        // `css` bleibt, weil es das Rendern blockiert. `js` ist das, was den Kopf
        // sprengt — die Bausteine entdeckt der Browser ohnehin über die Skript-Tags.
        const t = readFileSync(HOOK, "utf8")
        expect(t).toMatch(/preload:\s*\(\{\s*type\s*\}\)\s*=>\s*type\s*===\s*['"]css['"]/)
    })

    it("⚠️ ein Filter auf `!== 'js'` wäre schlimmer als gar keiner", () => {
        // Gemessen: Er nimmt Schriften und Anhänge **hinzu**, die die Vorgabe
        // ausschließt — `/` wuchs damit von 2 460 auf 7 757 Bytes. Die naheliegende
        // Mitte war die schlechteste Wahl.
        expect(readFileSync(HOOK, "utf8")).not.toContain("type !== 'js'")
    })
})

describe("nginx als zweite Sicherung", () => {
    it("liest einen größeren Antwortkopf", () => {
        // Der eigentliche Fix sitzt an der Quelle; das hier fängt künftiges Wachstum ab
        // (Cookies, CSP, neue Header), damit kein 502 entsteht, den niemand erklärt.
        const conf = readFileSync(NGINX, "utf8")
        const block = conf.slice(conf.indexOf("location / {"))
        expect(block).toMatch(/proxy_buffer_size\s+\d+k/)
    })
})
