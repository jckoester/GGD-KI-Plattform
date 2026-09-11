/**
 * Farbregeln der Oberfläche — projektweit geprüft, nicht je Komponente.
 *
 * Geprüft wird **eine** Paarung: Akzent als Schrift auf seiner eigenen
 * Nachbarstufe (`bg-*-re-2` + `text-*-re`). Sie ergibt 1,45–1,48:1 bei einer
 * Untergrenze von 4,5:1 und war so in den Schweregrad-Chips von `/flags` und
 * `/review` gebaut (behoben 10.09.2026) — also keine ausgedachte Gefahr.
 *
 * Sie steht hier allein, weil sie **eindeutig** ist: Es gibt keinen Fall, in dem
 * 1,45:1 vertretbar wäre, und der Bestand ist sauber. Eine zweite, breitere Regel
 * ist am 11.09.2026 wieder herausgeflogen — die Begründung unten im Test.
 *
 * ⚠️ **Kommentare werden vor der Prüfung entfernt.** Sonst findet der Test die
 * Erklärung, die über ihm steht — genau so war die erste Fassung des
 * Picker-Wächters wertlos (`picker_tastatur.test.js`), und genau so stolperte die
 * Wortsuche im Krisen-Mailtext über ihren eigenen Erklärsatz. Ein Wächter darf
 * nicht messen, was über ihn geschrieben steht.
 *
 * Die Datei lag bis 11.09.2026 in `crisis_labels.test.js` — dort war sie am Anlass
 * festgemacht, nicht an der Regel.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(dirname(fileURLToPath(import.meta.url))); // src/lib → src
const KUERZEL = ["re", "or", "ye", "gr", "cy", "bl", "pu", "ma"];

/** Alle .svelte/.js-Dateien unter src/ einsammeln. */
function quelldateien(wurzel) {
    const gefunden = [];
    for (const eintrag of readdirSync(wurzel)) {
        const pfad = join(wurzel, eintrag);
        if (statSync(pfad).isDirectory()) {
            gefunden.push(...quelldateien(pfad));
        } else if (/\.(svelte|js)$/.test(eintrag) && !/\.test\.js$/.test(eintrag)) {
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

/**
 * Sucht in jeder Klassenliste nach einer Fläche und einer Schrift desselben Modus
 * und derselben Farbfamilie.
 *
 * Geprüft wird innerhalb **einer** Klassenliste, nicht bloß beides irgendwo in der
 * Datei: Eine Datei darf die Fläche an einer und die Schrift an ganz anderer Stelle
 * verwenden, ohne dass sie je aufeinandertreffen.
 */
function paarungen(flaechenSuffix) {
    const dateien = quelldateien(SRC);
    expect(dateien.length).toBeGreaterThan(50); // der Lauf hat wirklich gesucht

    const treffer = [];
    for (const pfad of dateien) {
        const inhalt = ohneKommentare(readFileSync(pfad, "utf8"));
        const listen =
            inhalt.match(/(["'`])[^"'`]*\b(?:bg|text)-(?:light|dark)-[^"'`]*\1/g) ?? [];
        for (const liste of listen) {
            for (const k of KUERZEL) {
                for (const modus of ["light", "dark"]) {
                    const flaeche = new RegExp(`bg-${modus}-${k}${flaechenSuffix}\\b`);
                    const schrift = new RegExp(`text-${modus}-${k}\\b(?!-)`);
                    if (flaeche.test(liste) && schrift.test(liste)) {
                        treffer.push(`${pfad.replace(SRC, "src")}: ${modus}-${k}`);
                    }
                }
            }
        }
    }
    return treffer;
}

describe("Farbregeln", () => {
    it("kein Akzent auf seiner eigenen Nachbarstufe (`-2` als Fläche)", () => {
        // `light-re-2` ist derselbe Farbwert wie `dark-re` (red-400) — die beiden
        // liegen eine Palettenstufe auseinander. 1,45–1,48:1.
        expect(paarungen("-2")).toEqual([]);
    });

    // ⚠️ **Hier stand kurzzeitig eine zweite Regel — „kein Akzent als Schrift auf
    // `-bg`" — und sie ist wieder heraus.** Sie fand vier Stellen
    // (`AttachmentChip`, `MessageBubble`, `chat`, `library`), aber beim Nachmessen
    // trug ihre Begründung nicht: Die vier scheitern nicht an der **Tönung**,
    // sondern an der Akzentfarbe selbst. `text-dark-re` (red-400) erreicht im
    // Dunkelmodus auch auf dem blanken Seitenhintergrund nur 4,42:1; `library`
    // tönt überhaupt nur beim Hover.
    //
    // Eine Regel mit vier sofortigen Ausnahmen ist keine Regel, sondern Theater.
    // Der wirkliche Befund ist breiter und steht in der Todo (*UI / Frontend*):
    // Akzentfarben und `tx-2` erreichen als Schrift durchweg keine 4,5:1 —
    // gelb hell 3,01 · grün hell 3,81 · orange hell 4,03 · rot dunkel 4,09 ·
    // `tx-2` hell 3,20–4,47 je nach Fläche. Das ist eine Entscheidung über die
    // Palette, nicht über einzelne Klassenlisten, und sie gehört nicht in einen
    // Test, der sie nebenbei erzwingt.
    //
    // Was stattdessen wirkt: Der Kommentar bei den `-bg`-Token in
    // `routes/layout.css` sagt, welche Schrift daraufgehört — dort liest ihn, wer
    // das Token verwendet.

    it("die Suche greift überhaupt in Klassenlisten", () => {
        // Gegenprobe gegen den stummen Fehlschlag: Wenn das Muster für Klassenlisten
        // nicht mehr passt (andere Schreibweise, anderes Anführungszeichen), fände
        // der Test nie etwas und bliebe für immer grün.
        const kunstgriff = `class="px-2 bg-light-or-2 text-light-or rounded"`;
        const listen =
            kunstgriff.match(/(["'`])[^"'`]*\b(?:bg|text)-(?:light|dark)-[^"'`]*\1/g) ?? [];
        expect(listen).toHaveLength(1);
        expect(/bg-light-or-2\b/.test(listen[0])).toBe(true);
        expect(/text-light-or\b(?!-)/.test(listen[0])).toBe(true);
    });

    it("entfernt Kommentare, bevor sie als Code zählen", () => {
        const mitKommentar = `
            // früher stand hier class="bg-light-ye-bg text-light-ye"
            /* und hier auch: "bg-light-gr-bg text-light-gr" */
            <!-- und hier: "bg-light-re-bg text-light-re" -->
        `;
        expect(ohneKommentare(mitKommentar).trim()).toBe("");
    });
});
