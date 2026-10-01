import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load } from "js-yaml";

// repo/frontend/src/lib → repo/config
const WURZEL = dirname(dirname(dirname(dirname(fileURLToPath(import.meta.url)))));
const BEISPIEL = join(WURZEL, "config", "crisis_triggers.example.yaml");
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

    it("beschriftet die Kategorie „letalitaet\" lesbar", () => {
        // Ohne Eintrag stünde der Schlüssel in der Tabelle — lesbar, aber roh.
        expect(categoryLabel("letalitaet")).toBe("Tödliche Menge");
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

    it("beschriftet jede ausgelieferte Kategorie", () => {
        // ⚠️ Vorher stand hier `toHaveLength(5)`. Das prüfte die Anzahl, nicht die
        // Sache: Eine neue Kategorie im Backend ließ den Test scheitern, ohne zu
        // sagen welche — und eine Umbenennung wäre unbemerkt durchgegangen.
        // Jetzt ist die ausgelieferte Vorlage der Maßstab (Paket 1 von 0.12, AP2).
        const yaml = load(readFileSync(BEISPIEL, "utf8"));
        const kategorien = yaml.triggers.map((t) => t.category);
        expect(kategorien.length).toBeGreaterThan(0);
        for (const k of kategorien) {
            expect(CATEGORY, `Kategorie '${k}' hat keine Beschriftung`).toHaveProperty(k);
        }
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

// Die allgemeinen Farbregeln, die hier bis 11.09.2026 mitliefen, stehen jetzt in
// `farbregeln.test.js` — sie gelten projektweit und haben mit Krisen-Beschriftungen
// nichts zu tun.
