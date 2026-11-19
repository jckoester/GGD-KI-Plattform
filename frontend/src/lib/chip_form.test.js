/** Chips über dem Chat-Eingabefeld in der Form der Kontext-Chips (0.49, H5). */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
    AKZENT_BLAU, CHIP_AKZENT, CHIP_FORM, CHIP_ICON, ZWEI_ZEILEN_PX, chipKlasse, fachAkzentStil, versteckteChips,
} from "./chip_form.js";

describe("fachAkzentStil", () => {
    it("Rand links voll, rundum zart, Grund zu 10 % getönt", () => {
        expect(fachAkzentStil("#3b82f6")).toBe(
            "border-color: #3b82f640; border-left-color: #3b82f6; background-color: #3b82f61a",
        );
    });

    it("leer ohne gültigen Hexwert — nichts Fremdes gelangt in `style`", () => {
        for (const farbe of [null, undefined, "", "blue", "#fff", "border-light-ui-3", "#3b82f6; color: red"]) {
            expect(fachAkzentStil(farbe)).toBe("");
        }
    });
});

describe("chipKlasse", () => {
    it("ohne Fachfarbe der blaue Akzent der Kontext-Chips", () => {
        expect(chipKlasse(null)).toBe(`${CHIP_FORM} ${AKZENT_BLAU}`);
        expect(chipKlasse("#10b981")).toBe(CHIP_FORM);
    });

    it("D-Form: links fast eckig mit Akzentrand, rechts rund; Rand nie in Schriftfarbe", () => {
        expect(CHIP_FORM).toMatch(/\brounded-l-sm\b/);
        expect(CHIP_FORM).toMatch(/\brounded-r-full\b/);
        expect(CHIP_FORM).not.toMatch(/\brounded-full\b/);
        expect(CHIP_FORM).not.toMatch(/\bbg-/);
        // Balken kräftig, dafür links weniger Abstand (Jan, 19.11.2026).
        expect(CHIP_FORM).toMatch(/\bborder-l-4\b/);
        expect(CHIP_FORM).toMatch(/\bpl-1\.5\b/);
        // Jeder Akzent setzt die Randfarbe rundum selbst (Tailwind 4: sonst currentColor).
        for (const [k, klassen] of Object.entries(CHIP_AKZENT)) {
            if (k === "neutral") continue;
            expect(klassen).toMatch(new RegExp(`\\bborder-light-${k}/30\\b`));
            expect(klassen).toMatch(new RegExp(`\\bborder-l-light-${k}\\b`));
            expect(klassen).toMatch(new RegExp(`\\bbg-light-${k}/10\\b`));
        }
        expect(AKZENT_BLAU).toBe(CHIP_AKZENT.bl);
        expect(fachAkzentStil("#10b981")).toMatch(/^border-color: /);
    });

    it("Schrift in voller Stärke (`tx`), nicht `tx-2`", () => {
        expect(CHIP_FORM).toMatch(/\btext-light-tx\b(?!-)/);
        expect(CHIP_FORM).not.toMatch(/text-light-tx-2/);
    });
});

describe("Kontext-Chips", () => {
    it("nutzen dieselbe Form und Akzente", () => {
        const kontext = readFileSync(
            join(dirname(fileURLToPath(import.meta.url)), "components", "ContextChips.svelte"),
            "utf8",
        );
        expect(kontext).toContain('class="{CHIP_FORM} {accentClass}"');
        expect(kontext).toContain("CHIP_AKZENT[colorToken]");
        expect(kontext).not.toMatch(/const CHIP_ACCENT/);
    });
});

describe("Produkte und Anhänge (Jan, 19.11.2026: alle Chips über dem Eingabefeld)", () => {
    const lies = (name) => readFileSync(
        join(dirname(fileURLToPath(import.meta.url)), "components", name), "utf8",
    );

    it("Produkte aus der Werkstatt: D-Form, Akzent wie „Material“", () => {
        const q = lies("ProduktChips.svelte");
        expect(q).toContain('class="{CHIP_FORM} {CHIP_AKZENT[CATEGORY_COLORS.artifact]}"');
        expect(q).toContain("<Hammer size={CHIP_ICON}");
        expect(q).not.toMatch(/rounded-full/);
    });

    it("hochgeladene Dateien: D-Form, neutral; Fehler rot", () => {
        const q = lies("AttachmentChip.svelte");
        expect(q).toContain("{CHIP_FORM} {status === 'error' ? CHIP_AKZENT.re : CHIP_AKZENT.neutral}");
        expect(q.match(/size=\{CHIP_ICON\}/g)).toHaveLength(3);
        expect(q).not.toMatch(/px-2 py-1 rounded-full/);
    });
});

describe("Chat-Seite", () => {
    const SEITE = readFileSync(
        join(dirname(fileURLToPath(import.meta.url)), "..", "routes", "(app)", "chat", "+page.svelte"),
        "utf8",
    );

    it("Icons in allen Chips gleich groß (Jan, 19.11.2026)", () => {
        expect(CHIP_ICON).toBe(14);
        expect(SEITE).toContain("<Bot size={CHIP_ICON}");
        const fach = SEITE.slice(SEITE.indexOf("class={chipKlasse(subj?.color)}"));
        expect(fach.slice(0, 600)).toContain("size={CHIP_ICON}");
        const kontext = readFileSync(
            join(dirname(fileURLToPath(import.meta.url)), "components", "ContextChips.svelte"),
            "utf8",
        );
        expect(kontext).toContain("iconSize={CHIP_ICON}");
    });

    it("Assistent- und Fach-Chip nutzen die gemeinsame Form", () => {
        expect(SEITE.match(/class=\{chipKlasse\(/g)).toHaveLength(2);
        expect(SEITE.match(/style=\{fachAkzentStil\(/g)).toHaveLength(2);
    });

    it("Anordnung (0.49, Jan 19.11.2026): Chat-Bezug über, Nachrichtenbezug unter der Eingabe", () => {
        const eingabe = SEITE.indexOf("<textarea");
        expect(eingabe).toBeGreaterThan(0);
        // über der Eingabe: Assistent und Fach
        expect(SEITE.indexOf("<Bot size={CHIP_ICON}")).toBeLessThan(eingabe);
        expect(SEITE.indexOf("class={chipKlasse(subj?.color)}")).toBeLessThan(eingabe);
        // darunter: Bausteine, Produkte, Uploads
        expect(SEITE.indexOf("<NachrichtenChips")).toBeGreaterThan(eingabe);
        expect(SEITE.split("<NachrichtenChips")).toHaveLength(2);
        for (const teil of ["<ContextChips", "<ProduktChips", "<AttachmentChip"]) {
            expect(SEITE).not.toContain(teil);
        }
    });

    it("keine Tailwind-Klassen als CSS-Wert im `style`", () => {
        expect(SEITE).not.toMatch(/style="[^"]*border-light-ui-3/);
    });
});

describe("NachrichtenChips (Jan 19.11.2026: eine Reihe, eingeklappt drei Zeilen)", () => {
    const lies = (name) => readFileSync(
        join(dirname(fileURLToPath(import.meta.url)), "components", name), "utf8",
    );
    const Q = lies("NachrichtenChips.svelte");

    it("Bausteine, Produkte und Anhänge stehen in einem Rahmen", () => {
        const rahmen = Q.slice(Q.indexOf("bind:this={feld}"), Q.indexOf("{#if hatMehr}"));
        for (const teil of ["<ContextChips", "<ProduktChips", "<AttachmentChip"]) {
            expect(rahmen).toContain(teil);
        }
    });

    it("die Teile bringen keinen eigenen Rahmen mit (sonst bricht die Reihe)", () => {
        for (const name of ["ContextChips.svelte", "ProduktChips.svelte"]) {
            const markup = lies(name).split("</script>")[1];
            expect(markup.trim()).toMatch(/^(<!--[\s\S]*?-->\s*)?\{#each/);
        }
    });

    it("klappt nur ein, wenn es knapp ist (Jan 19.11.2026)", () => {
        expect(Q).toMatch(/einklappen && !offen\s*\?\s*'max-h-\[3\.75rem\] overflow-hidden'/);
        expect(Q).toContain("hatMehr = einklappen && ");
        const SEITE = readFileSync(
            join(dirname(fileURLToPath(import.meta.url)), "..", "routes", "(app)", "chat", "+page.svelte"),
            "utf8",
        );
        expect(SEITE).toContain("einklappen={kompakt}");
    });

    it("eingeklappt zwei Zeilen hoch, passend zu ZWEI_ZEILEN_PX", () => {
        expect(Q).toContain("max-h-[3.75rem] overflow-hidden");
        expect(3.75 * 16).toBe(ZWEI_ZEILEN_PX);
    });

    it("versteckteChips zählt die Kinder unterhalb des Rahmens", () => {
        const kind = (offsetTop) => ({ offsetTop });
        const feld = { clientHeight: 60, children: [kind(0), kind(0), kind(32), kind(64), kind(96)] };
        expect(versteckteChips(feld)).toBe(2);
        expect(versteckteChips(null)).toBe(0);
    });
});
