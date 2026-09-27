/**
 * Wächter: Wer eine Seitenleiste als Overlay führt, muss sie beim Navigieren zuklappen.
 *
 * **Der Befund dahinter** (Telefontest, 18.09.2026): Auf kleinen Bildschirmen liegt die
 * Seitenleiste **über** der Seite. Tippte man einen Eintrag an, wechselte die Seite
 * dahinter — sichtbar blieb das Menü. Zwei Tipps für jede Navigation, und nichts im
 * Code deutete darauf hin: `closeSidebar()` existierte, wurde aber nur vom
 * Hintergrund-Klick gerufen.
 *
 * ⚠️ **Warum Quelltext statt Verhalten.** Das Projekt hat keine Svelte-Komponententests;
 * ein Layout zu mounten verlangte `@testing-library/svelte` samt Navigationsattrappe,
 * und jede neue Abhängigkeit trägt hier eine Obergrenze (Sicherheits-Audit #17).
 * Dieselbe Begründung wie in `picker_tastatur.test.js`.
 *
 * Der Test **sucht** die Layouts, statt sie aufzuzählen: Ein drittes Layout mit eigener
 * Seitenleiste ist genau der Fall, in dem die Regel sonst wieder verlorenginge.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROUTES = join(dirname(fileURLToPath(import.meta.url)), "..", "routes");

function layoutsMitSeitenleiste(verzeichnis = ROUTES, gefunden = []) {
    for (const eintrag of readdirSync(verzeichnis, { withFileTypes: true })) {
        const pfad = join(verzeichnis, eintrag.name);
        if (eintrag.isDirectory()) layoutsMitSeitenleiste(pfad, gefunden);
        else if (eintrag.name === "+layout.svelte") {
            const quelle = readFileSync(pfad, "utf-8");
            if (quelle.includes("sidebarOpen")) {
                gefunden.push({ pfad: relative(ROUTES, pfad), quelle });
            }
        }
    }
    return gefunden;
}

const LAYOUTS = layoutsMitSeitenleiste();

/** Der Rumpf des `afterNavigate`-Aufrufs — oder `null`, wenn es ihn nicht gibt. */
function navigationsRumpf(quelle) {
    const ab = quelle.indexOf("afterNavigate(");
    if (ab === -1) return null;
    const bis = quelle.indexOf("});", ab);
    return bis === -1 ? null : quelle.slice(ab, bis);
}

describe("Seitenleiste beim Navigieren", () => {
    it("findet die Layouts überhaupt", () => {
        // Ohne diese Prüfung liefe eine leere Fundliste als bestandener Test durch —
        // derselbe Fehlertyp wie ein `indexOf`, das mit -1 zufrieden ist.
        expect(LAYOUTS.length).toBeGreaterThanOrEqual(2);
    });

    it.each(LAYOUTS.map((l) => [l.pfad, l.quelle]))(
        "%s klappt sie beim Seitenwechsel zu",
        (_pfad, quelle) => {
            expect(quelle).toContain("afterNavigate");
            const rumpf = navigationsRumpf(quelle);
            expect(rumpf).not.toBeNull();
            expect(rumpf).toContain("sidebarOpen = false");
        },
    );

    it.each(LAYOUTS.map((l) => [l.pfad, l.quelle]))(
        "%s lässt sie am Schreibtisch offen",
        (_pfad, quelle) => {
            // Ohne die Abfrage klappte die feste Seitenleiste bei jedem Klick zu —
            // ein Rückschritt, der niemandem auf dem Telefon auffiele.
            expect(navigationsRumpf(quelle)).toContain("!isDesktop");
        },
    );
});
