import { describe, it, expect } from "vitest";
import {
    anteil,
    kalenderwoche,
    summe,
    sortiere,
    alsCsv,
    wochenCsv,
    knotenCsv,
} from "./vorabstatistik.js";

describe("vorabstatistik", () => {
    it("zeigt Anteile mit Zähler und Nenner, ohne Nenner einen Strich", () => {
        expect(anteil(3, 4)).toBe("3/4 (75 %)");
        expect(anteil(0, 5)).toBe("0/5 (0 %)");
        expect(anteil(0, 0)).toBe("—");
    });

    it("nennt die ISO-Kalenderwoche, auch über den Jahreswechsel", () => {
        expect(kalenderwoche("2026-10-12")).toBe("KW 42/2026");
        expect(kalenderwoche("2030-01-07")).toBe("KW 2/2030");
        // Montag 29.12.2025 gehört zur KW 1/2026 — der Donnerstag liegt schon im neuen Jahr.
        expect(kalenderwoche("2025-12-29")).toBe("KW 1/2026");
        expect(kalenderwoche("2026-12-28")).toBe("KW 53/2026");
    });

    it("summiert die Wochenzeilen", () => {
        const s = summe([
            { nachrichten: 4, mit_angebot: 3, angebot_nachgeschlagen: 1 },
            { nachrichten: 2, mit_angebot: 1, angebot_nachgeschlagen: 1 },
        ]);
        expect([s.nachrichten, s.mit_angebot, s.angebot_nachgeschlagen, s.mit_sicher]).toEqual([
            6, 4, 2, 0,
        ]);
    });

    const knoten = [
        { titel: "Probe", angeboten: 10, nachgeschlagen: 0, sicher: 0 },
        { titel: "Ion", angeboten: 0, nachgeschlagen: 0, sicher: 7 },
        { titel: "Stoffe", angeboten: 4, nachgeschlagen: 3, sicher: 1 },
    ];

    it("sortiert nach Anteil — Knoten ohne Angebot ans Ende, in beide Richtungen", () => {
        expect(sortiere(knoten, "anteil").map((k) => k.titel)).toEqual(["Stoffe", "Probe", "Ion"]);
        expect(sortiere(knoten, "anteil", false).map((k) => k.titel)).toEqual([
            "Probe",
            "Stoffe",
            "Ion",
        ]);
    });

    it("sortiert nach angeboten und sicher, ohne die Eingabe zu ändern", () => {
        const vorher = knoten.map((k) => k.titel);
        expect(sortiere(knoten, "angeboten").map((k) => k.titel)).toEqual(["Probe", "Stoffe", "Ion"]);
        expect(sortiere(knoten, "sicher").map((k) => k.titel)).toEqual(["Ion", "Stoffe", "Probe"]);
        expect(knoten.map((k) => k.titel)).toEqual(vorher);
    });

    it("schreibt CSV mit BOM, Semikolon und maskierten Feldern", () => {
        const csv = alsCsv(["a", "b"], [['Zitat "x"', "1;2"], [null, 3]]);
        expect(csv).toBe('﻿a;b\r\n"Zitat ""x""";"1;2"\r\n;3\r\n');
    });

    it("exportiert Wochen und Knoten mit allen Spalten", () => {
        const w = wochenCsv([{ woche: "2030-01-07", nachrichten: 4, mit_sicher: 2 }]);
        expect(w.split("\r\n")[0]).toBe(
            "﻿woche;nachrichten;mit_sicher;mit_angebot;angebot_nachgeschlagen;" +
                "angebot_ohne_sicher;angebot_ohne_sicher_nachgeschlagen;suchen_ohne_angebot",
        );
        expect(w.split("\r\n")[1]).toBe("2030-01-07;4;2;;;;;");
        const k = knotenCsv([
            { node_id: "x", titel: null, fach: "Chemie", sicher: 0, angeboten: 2, nachgeschlagen: 1 },
        ]);
        expect(k.split("\r\n")[1]).toBe("x;;Chemie;0;2;1");
    });
});
