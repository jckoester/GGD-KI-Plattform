/**
 * Der Knopf an der Antwort heißt „Als Dokument bearbeiten", nicht mehr „In Werkstatt
 * öffnen" (0.12, Entscheidung F5). „Werkstatt" bleibt der Name der **Ansicht**; der
 * Knopf nennt die Tätigkeit. Ein Rest des alten Texts in Oberfläche oder Doku hieße, dass
 * Anleitung und Knopf auseinanderlaufen — die Hilfe beschriebe einen Knopf, den es nicht
 * gibt.
 *
 * Nicht durchsucht: das CHANGELOG (es ist Geschichte) und diese Datei.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIESE = fileURLToPath(import.meta.url);
const SRC = dirname(dirname(DIESE));
const WURZEL = join(SRC, "..", "..");

// `\s+`, damit ein Zeilenumbruch mitten im Text den Rest nicht versteckt.
const ALT = /In\s+(der\s+)?Werkstatt\s+öffnen|in\s+die\s+Werkstatt\s+übernommen/i;

function dateien(ordner, endungen) {
    return readdirSync(ordner).flatMap((name) => {
        if (name === "node_modules" || name === "__pycache__") return [];
        const pfad = join(ordner, name);
        if (statSync(pfad).isDirectory()) return dateien(pfad, endungen);
        return endungen.some((e) => name.endsWith(e)) && pfad !== DIESE ? [pfad] : [];
    });
}

describe("Knopftext „Als Dokument bearbeiten“", () => {
    it("der alte Text steht nirgends mehr — Oberfläche, Doku, Backend-Kommentare", () => {
        const fundstellen = [
            ...dateien(SRC, [".svelte", ".js"]),
            ...dateien(join(WURZEL, "docs"), [".md"]),
            ...dateien(join(WURZEL, "backend", "app"), [".py"]),
        ].filter((p) => ALT.test(readFileSync(p, "utf8")));
        expect(fundstellen).toEqual([]);
    });

    it("der Knopf trägt den neuen Text, und die Anleitung nennt ihn", () => {
        const knopf = readFileSync(join(SRC, "lib", "components", "MessageBubble.svelte"), "utf8");
        const anleitung = readFileSync(join(WURZEL, "docs", "user", "werkstatt.md"), "utf8");
        expect(knopf).toContain("'Als Dokument bearbeiten'");
        expect(anleitung).toContain("„Als Dokument bearbeiten\"");
    });
});
