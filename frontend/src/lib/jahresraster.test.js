/**
 * Welche Halbjahre eine Übernahme anlegt (AP2, 22.09.2026).
 *
 * Die Entscheidung liegt im Modul, damit sie prüfbar ist: Beide Bauteile —
 * Sammelübernahme und Mustereditor — müssen dieselbe Antwort bekommen, und die
 * Vorläufigkeit muss bis in die Nutzlast durchreichen. Läuft eines der beiden auseinander,
 * entsteht ein zweites Halbjahr, das aussieht wie ein bestätigtes.
 */
import { describe, it, expect } from "vitest";
import {
    halbjahrFuerMuster,
    halbjahreFuerUebernahme,
    restjahrMoeglich,
    slotMeldung,
    vierzehntaegigWarnung,
} from "./jahresraster.js";

describe("restjahrMoeglich", () => {
    it("gilt nur im ersten Halbjahr", () => {
        expect(restjahrMoeglich(1)).toBe(true);
        expect(restjahrMoeglich(2)).toBe(false);
    });
});

describe("halbjahreFuerUebernahme", () => {
    it("ohne Auswahl nur das laufende Halbjahr", () => {
        expect(halbjahreFuerUebernahme(1)).toEqual([{ halbjahr: 1, vorlaeufig: false }]);
    });

    it("mit Auswahl beide, das zweite vorläufig", () => {
        expect(halbjahreFuerUebernahme(1, true)).toEqual([
            { halbjahr: 1, vorlaeufig: false },
            { halbjahr: 2, vorlaeufig: true },
        ]);
    });

    it("im zweiten Halbjahr bleibt die Auswahl wirkungslos", () => {
        // Es gibt kein Restjahr mehr — und „vorläufig" auf das laufende Halbjahr zu
        // schreiben wäre falsch: Dafür liegt der echte Stundenplan vor.
        expect(halbjahreFuerUebernahme(2, true)).toEqual([{ halbjahr: 2, vorlaeufig: false }]);
    });

    it("das laufende Halbjahr ist nie vorläufig", () => {
        for (const bis of [false, true]) {
            expect(halbjahreFuerUebernahme(1, bis)[0].vorlaeufig).toBe(false);
        }
    });
});

describe("halbjahrFuerMuster", () => {
    it("schreibt das Muster nur für das laufende Halbjahr", () => {
        // Ein nach HJ2 kopiertes Muster sähe wie eine Zusage aus; der Generator fällt
        // von sich aus auf HJ1 zurück und meldet das.
        expect(halbjahrFuerMuster(1)).toBe(1);
        expect(halbjahrFuerMuster(2)).toBe(2);
    });
});

describe("slotMeldung", () => {
    it("benennt das vorläufige Halbjahr als solches", () => {
        const text = slotMeldung({ created: 18, halbjahr: 2, vorlaeufig: true });
        expect(text).toContain("vorläufig");
        expect(text).toContain("18");
    });

    it("beim laufenden Halbjahr ohne Zusatz", () => {
        expect(slotMeldung({ created: 18, halbjahr: 1 })).not.toContain("vorläufig");
    });

    it("Einzahl bei einer Stunde", () => {
        expect(slotMeldung({ created: 1, halbjahr: 1 })).toContain("1 Stunde im");
    });
});

describe("vierzehntaegigWarnung", () => {
    it("schweigt, wenn kein Rückfall stattfand", () => {
        expect(vierzehntaegigWarnung({ fallback_vierzehntaegig: false })).toBeNull();
        expect(vierzehntaegigWarnung(null)).toBeNull();
    });

    it("nennt die Verschiebung und den Weg heraus", () => {
        const text = vierzehntaegigWarnung({ fallback_vierzehntaegig: true });
        expect(text).toContain("14-tägige");
        expect(text).toContain("eine Woche");
        expect(text).toContain("neu aus dem Stundenplan");
    });
});


// ── Verdrahtung ──────────────────────────────────────────────────────────────
//
// ⚠️ Quelltext statt Verhalten: Das Projekt hat keine Svelte-Komponententests
// (Begründung in `picker_tastatur.test.js`). Geprüft wird die eine Drift, die hier
// wirklich schadet — ein Aufruf, der das zweite Halbjahr erzeugt, **ohne** es als
// vorläufig zu kennzeichnen. Es sähe dann aus wie ein bestätigtes, und der Neuaufbau
// im Februar käme ohne Vorwarnung.

import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = dirname(fileURLToPath(import.meta.url));
const lies = (p) => readFileSync(join(SRC, p), "utf-8");

const SAMMEL = lies("components/StundenrasterUebernahme.svelte");
const EDITOR = lies("components/planner/PatternEditor.svelte");

describe("Beide Einstiege benutzen dasselbe Modul", () => {
    it.each([
        ["StundenrasterUebernahme", SAMMEL],
        ["PatternEditor", EDITOR],
    ])("%s liest die Regeln aus jahresraster.js", (_name, quelle) => {
        expect(quelle).toContain("$lib/jahresraster.js");
        expect(quelle).toContain("restjahrMoeglich");
    });

    it("die Sammelübernahme erzeugt je Halbjahr aus der Modul-Antwort", () => {
        // Nicht zwei fest verdrahtete Aufrufe, sondern eine Schleife über
        // `halbjahreFuerUebernahme` — sonst driften Auswahl und Wirkung auseinander.
        expect(SAMMEL).toContain("halbjahreFuerUebernahme");
        expect(SAMMEL).toContain("lauf.vorlaeufig");
    });

    it("das Muster wird nur für das laufende Halbjahr geschrieben", () => {
        // Ein nach HJ2 kopiertes Muster sähe wie eine Zusage aus.
        //
        // ⚠️ Geprüft wird die **Aufrufstelle**, nicht das Vorkommen des Namens: Ein
        // `toContain("halbjahrFuerMuster")` ist schon durch die Importzeile erfüllt. Beim
        // Gegenprüfen kam der Test deshalb grün zurück, obwohl der Aufruf eine fest
        // verdrahtete 2 trug.
        const aufrufe = [...SAMMEL.matchAll(/setWeekPattern\(([^)]*)\)/g)].map((m) => m[1]);
        expect(aufrufe.length).toBeGreaterThan(0);
        for (const args of aufrufe) {
            expect(args).toContain("musterHalbjahr");
        }
    });

    it("kein generateSlots-Aufruf auf das 2. Halbjahr ohne Kennzeichen", () => {
        for (const [name, quelle] of [["Sammel", SAMMEL], ["Editor", EDITOR]]) {
            for (const treffer of quelle.matchAll(/generateSlots\(([^)]*)\)/g)) {
                const args = treffer[1];
                if (/\b2\b/.test(args)) {
                    expect(args, `${name}: ${args}`).toMatch(/true\s*\)?$|vorlaeufig/);
                }
            }
        }
    });
});

