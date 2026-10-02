// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { token, beobachteModus } from "./diagrammfarben.js";

describe("diagrammfarben", () => {
    beforeEach(() => {
        document.documentElement.style.setProperty("--diagramm-verbrauch", "#205ea6");
        document.documentElement.classList.remove("dark");
    });

    it("liest eine Rolle als CSS-Variable", () => {
        // ⚠️ Das prüft nur den **Mechanismus** — die Variable setzt der Test selbst. Ob es
        // sie zur Laufzeit gibt, prüft der Wächter unten an `layout.css`. Die erste
        // Fassung hatte nur diesen Test und bestand, während die Soll-Linie schwarz war.
        expect(token("verbrauch")).toBe("#205ea6");
    });

    it("liefert für eine unbekannte Rolle einen leeren Wert", () => {
        expect(token("gibtesnicht")).toBe("");
    });

    it("meldet das Umschalten, damit neu gezeichnet wird", async () => {
        let gemeldet = 0;
        const abmelden = beobachteModus(() => gemeldet++);
        document.documentElement.classList.add("dark");
        await new Promise((r) => setTimeout(r, 0));
        expect(gemeldet).toBe(1);
        abmelden();
        document.documentElement.classList.remove("dark");
        await new Promise((r) => setTimeout(r, 0));
        expect(gemeldet).toBe(1);
    });
});

// ── Wächter: Diagramme nehmen ihre Farben aus den Tokens ──────────────────────
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(dirname(fileURLToPath(import.meta.url)));

function svelteDateien(ordner) {
    return readdirSync(ordner).flatMap((name) => {
        const pfad = join(ordner, name);
        if (statSync(pfad).isDirectory()) return svelteDateien(pfad);
        return name.endsWith(".svelte") ? [pfad] : [];
    });
}

/** Quelltext ohne Kommentare — sonst prüfte der Wächter seine eigene Begründung. */
function ohneKommentare(text) {
    return text
        .replace(/<!--[\s\S]*?-->/g, "")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

describe("Diagramme ohne fest verdrahtete Farben", () => {
    const mitDiagramm = svelteDateien(SRC).filter((p) =>
        readFileSync(p, "utf8").includes('import("chart.js")'),
    );

    it("findet die Diagramme überhaupt", () => {
        // Sonst bestünde der Test auch dann, wenn die Suche ins Leere läuft.
        expect(mitDiagramm.length).toBeGreaterThanOrEqual(2);
    });

    it.each(mitDiagramm.map((p) => [p.slice(SRC.length + 1), p]))(
        "%s nimmt Farben aus den Tokens",
        (_name, pfad) => {
            // ⚠️ Bis 0.12 stand in `statistics/costs` ein Olivgrün als `rgba(…)` — eine
            // Statusfarbe, an keinen Modus gebunden. Diagramme lesen ihre Farben über
            // `token()` aus `diagrammfarben.js`.
            const code = ohneKommentare(readFileSync(pfad, "utf8"));
            expect(code).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
            expect(code).not.toMatch(/rgba?\(/);
        },
    );
});

// ── Wächter: Jede verwendete Rolle gibt es zur Laufzeit — hell UND dunkel ────────

/** Inhalt des ersten Blocks, der mit `kopf` beginnt (`:root {` / `.dark {`). */
function block(css, kopf) {
    const i = css.search(new RegExp(`^${kopf.replace(".", "\\.")}\\s*\\{`, "m"));
    if (i < 0) return "";
    const start = css.indexOf("{", i) + 1;
    let tiefe = 1;
    for (let j = start; j < css.length; j++) {
        if (css[j] === "{") tiefe++;
        if (css[j] === "}" && --tiefe === 0) return css.slice(start, j);
    }
    return "";
}

describe("Diagrammrollen in layout.css", () => {
    const css = readFileSync(join(SRC, "routes", "layout.css"), "utf8");
    const hell = block(css, ":root");
    const dunkel = block(css, ".dark");
    const rollen = [
        ...new Set(
            svelteDateien(SRC)
                .map((p) => readFileSync(p, "utf8"))
                .flatMap((code) => [...code.matchAll(/\btoken\("([a-z-]+)"\)/g)].map((m) => m[1])),
        ),
    ];

    it("findet die verwendeten Rollen überhaupt", () => {
        expect(rollen.length).toBeGreaterThanOrEqual(4);
    });

    it.each(rollen)("--diagramm-%s ist hell und dunkel definiert", (rolle) => {
        // ⚠️ **In `:root` und `.dark`, nicht in `@theme inline`.** Dort war
        // `--color-light-or` zwar definiert, Tailwind gab es aber nicht aus, weil kein
        // `var(…)` darauf verwies — die Soll-Linie wurde schwarz. Ein Wächter, der nur
        // „steht irgendwo in layout.css" prüft, hätte das nicht gefunden.
        expect(hell).toMatch(new RegExp(`--diagramm-${rolle}\\s*:\\s*var\\(--color-light-`));
        expect(dunkel).toMatch(new RegExp(`--diagramm-${rolle}\\s*:\\s*var\\(--color-dark-`));
    });
});
