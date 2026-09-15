/**
 * Projektregel: Svelte 5 Runes, keine Alt-Syntax.
 *
 * `$:` und der Runes-Modus schließen einander aus — eine Datei, die beides mischt, lässt
 * sich nicht übersetzen, und eine Datei mit `$:` allein läuft im Legacy-Modus mit anderem
 * Reaktivitätsverhalten. Bis 15.09.2026 war genau eine Datei übrig
 * (`routes/info/[key]/+page.svelte`); sie fiel nur auf, weil ESLint dort vier
 * `infinite-reactive-loop`-Warnungen meldete. Ohne Wächter wäre die nächste ebenso lange
 * unbemerkt geblieben.
 *
 * ⚠️ **Kommentare werden vor der Prüfung entfernt.** Sonst fände der Test die Erklärung,
 * die über ihm steht — dieselbe Falle wie bei `farbregeln.test.js` und dem
 * Picker-Wächter. Ein Wächter darf nicht messen, was über ihn geschrieben steht.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(dirname(fileURLToPath(import.meta.url))); // src/lib → src

function svelteDateien(wurzel) {
    const gefunden = [];
    for (const eintrag of readdirSync(wurzel)) {
        const pfad = join(wurzel, eintrag);
        if (statSync(pfad).isDirectory()) {
            gefunden.push(...svelteDateien(pfad));
        } else if (eintrag.endsWith(".svelte")) {
            gefunden.push(pfad);
        }
    }
    return gefunden;
}

const ohneKommentare = (text) =>
    text
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/[^\n]*/gm, "")
        .replace(/<!--[\s\S]*?-->/g, "");

describe("Svelte-5-Runes", () => {
    it("keine Datei verwendet die Alt-Syntax $:", () => {
        const dateien = svelteDateien(SRC);
        expect(dateien.length).toBeGreaterThan(50); // der Lauf hat wirklich gesucht

        const treffer = dateien.filter((pfad) =>
            /^\s*\$:/m.test(ohneKommentare(readFileSync(pfad, "utf8"))),
        );
        expect(treffer.map((p) => p.slice(SRC.length + 1))).toEqual([]);
    });
});
