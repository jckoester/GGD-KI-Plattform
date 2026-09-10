import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import {
    SEVERITY,
    CATEGORY,
    severityLabel,
    severityClass,
    categoryLabel,
} from "./crisis_labels.js";

describe("crisis_labels", () => {
    it("beschriftet die drei Schweregrade", () => {
        expect(severityLabel("alert")).toBe("Alarm");
        expect(severityLabel("warning")).toBe("Warnung");
        expect(severityLabel("info")).toBe("Hinweis");
    });

    it("gibt einen unbekannten Schweregrad unverändert zurück", () => {
        // Ein neuer Grad im Backend soll sichtbar werden, nicht als leere Zelle
        // verschwinden.
        expect(severityLabel("panik")).toBe("panik");
        expect(categoryLabel("neue_kategorie")).toBe("neue_kategorie");
    });

    it("hat für einen unbekannten Schweregrad eine neutrale Fläche", () => {
        const cls = severityClass("panik");
        expect(cls).toContain("bg-light-ui-2");
        expect(cls).toContain("dark:bg-dark-ui-2");
    });

    it("beschriftet alle fünf Kategorien", () => {
        expect(Object.keys(CATEGORY)).toHaveLength(5);
        for (const label of Object.values(CATEGORY)) {
            expect(label).not.toMatch(/_/); // Anzeigetext, kein Schlüssel
        }
    });

    it("färbt Fläche und Rand, nicht die Schrift", () => {
        // Der Kontrastfehler (10.09.2026) bestand darin, den Akzent als Schrift
        // auf die Nachbarstufe derselben Palettenfamilie zu setzen. Die Klassen
        // dürfen deshalb **keine** Textfarbe mitbringen — die setzt die Seite mit
        // `text-light-tx`.
        for (const [grad, { cls }] of Object.entries(SEVERITY)) {
            expect(cls, grad).not.toMatch(/\btext-/);
            expect(cls, grad).toMatch(/\bbg-light-\w\w-bg\b/);
            expect(cls, grad).toMatch(/\bdark:bg-dark-\w\w-bg\b/);
            expect(cls, grad).toMatch(/\bborder-light-/);
        }
    });
});

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

describe("Farbregel: kein Akzent auf seiner eigenen Nachbarstufe", () => {
    // Die `-2`-Token sind der Akzent des *anderen* Modus: `light-re-2` = red-400 =
    // `dark-re`. Wer `bg-light-re-2` mit `text-light-re` kombiniert, schreibt
    // red-600 auf red-400 — 1,48:1 bei einer Untergrenze von 4,5:1. Genau so
    // waren die Schweregrad-Chips in `/flags` und `/review` gebaut.
    //
    // Der Test sucht das Paar innerhalb **einer** Klassenliste, nicht bloß beide
    // Token irgendwo in der Datei: Eine Datei darf `bg-light-re-2` für eine Fläche
    // und `text-light-re` an ganz anderer Stelle verwenden.
    const KUERZEL = ["re", "or", "ye", "gr", "cy", "bl", "pu", "ma"];

    const SRC = dirname(dirname(fileURLToPath(import.meta.url))); // src/lib → src

    it("findet in src/ keine solche Paarung", () => {
        const dateien = quelldateien(SRC);
        expect(dateien.length).toBeGreaterThan(50); // der Lauf hat wirklich gesucht

        const treffer = [];
        for (const pfad of dateien) {
            const inhalt = readFileSync(pfad, "utf8");
            // Klassenlisten grob abgreifen: class="…" / class:…={…} / Zeichenketten
            // mit mehreren Tailwind-Klassen.
            for (const liste of inhalt.match(/(["'`])[^"'`]*\b(?:bg|text)-(?:light|dark)-[^"'`]*\1/g) ?? []) {
                for (const k of KUERZEL) {
                    for (const modus of ["light", "dark"]) {
                        const flaeche = new RegExp(`bg-${modus}-${k}-2\\b`);
                        const schrift = new RegExp(`text-${modus}-${k}\\b(?!-)`);
                        if (flaeche.test(liste) && schrift.test(liste)) {
                            treffer.push(`${pfad}: ${modus}-${k}`);
                        }
                    }
                }
            }
        }
        expect(treffer).toEqual([]);
    });
});
