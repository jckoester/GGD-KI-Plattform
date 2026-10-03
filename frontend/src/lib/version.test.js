/**
 * Eine Zahl für die Plattformversion: `backend/VERSION` (0.13, P4).
 *
 * Bis 0.13 stand sie in `package.json`, wo das Backend sie nicht erreicht. Kommt dort
 * wieder eine `version` hinein, gibt es zwei Zahlen — und eine davon wird bei der
 * nächsten Release vergessen.
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const FRONTEND = dirname(dirname(dirname(fileURLToPath(import.meta.url))))

describe("Plattformversion", () => {
    it("package.json trägt keine eigene Version", () => {
        const pkg = JSON.parse(readFileSync(join(FRONTEND, "package.json"), "utf8"))
        const lock = JSON.parse(readFileSync(join(FRONTEND, "package-lock.json"), "utf8"))
        expect(pkg.version).toBeUndefined()
        expect(lock.version).toBeUndefined()
        expect(lock.packages[""].version).toBeUndefined()
    })

    it("vite liest sie aus backend/VERSION", () => {
        const config = readFileSync(join(FRONTEND, "vite.config.js"), "utf8")
        expect(config).toContain('new URL("../backend/VERSION", import.meta.url)')
    })

    it("die Quelle hat die Form x.y.z", () => {
        const v = readFileSync(join(FRONTEND, "..", "backend", "VERSION"), "utf8").trim()
        expect(v).toMatch(/^\d+\.\d+\.\d+$/)
    })
})
