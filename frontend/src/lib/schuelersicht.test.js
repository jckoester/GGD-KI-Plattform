import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it, expect } from "vitest";
import {
    GRUENDE, assistentLink, fachschaftHinweis, grundText, jahrgangText, jahrgangWaehlbar, stufenText,
} from "./schuelersicht.js";

describe("GRUENDE", () => {
    it("stimmt mit dem Backend überein und hat zu jedem Grund einen Text", () => {
        const quelle = readFileSync(
            resolve(__dirname, "../../../backend/app/assistants/sichtbarkeit.py"), "utf8");
        const block = quelle.match(/GRUENDE = frozenset\(\{([\s\S]*?)\}\)/)[1];
        const backend = [...block.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]).sort();
        expect([...GRUENDE].sort()).toEqual(backend);
        // Jeder Grund hat einen eigenen Text — keiner fällt auf „nicht freigegeben“ zurück.
        for (const g of GRUENDE.filter((g) => g !== "unbekannt")) {
            expect(grundText(g)).not.toBe(grundText("unbekannt"));
        }
    });
});

describe("grundText", () => {
    it("nennt bei der Klassenstufe die Grenzen", () => {
        expect(grundText("stufe", { min_grade: 11, max_grade: 13 })).toBe("für eine andere Klassenstufe (Klasse 11–13)");
        expect(grundText("stufe", {})).toBe("für eine andere Klassenstufe");
        expect(grundText("fachschaft")).toBe("nur für die Lehrkräfte der Fachschaft freigegeben");
    });
    it("fällt bei Unbekanntem auf „nicht freigegeben“ zurück", () => {
        expect(grundText("neu-im-backend")).toBe("nicht freigegeben");
    });
});

describe("stufenText", () => {
    it("liest die Grenzen", () => {
        expect(stufenText({ min_grade: 5, max_grade: 7 })).toBe("5–7");
        expect(stufenText({ min_grade: 9, max_grade: 9 })).toBe("9");
        expect(stufenText({ min_grade: 11 })).toBe("ab 11");
        expect(stufenText({ max_grade: 6 })).toBe("bis 6");
        expect(stufenText({})).toBeNull();
    });
});

describe("assistentLink", () => {
    it("eigene in den Editor, fremde in den Chat", () => {
        expect(assistentLink({ id: 4, eigen: true })).toBe("/assistants/my/4");
        expect(assistentLink({ id: 4, eigen: false })).toBe("/chat?assistant_id=4");
    });
});

describe("Jahrgang", () => {
    it("sagt, wofür gerechnet wurde", () => {
        expect(jahrgangText({ jahrgang: 9, jahrgang_quelle: "festgelegt" }))
            .toBe("Gerechnet für Klasse 9 (an der Gruppe festgelegt).");
        expect(jahrgangText({ jahrgang: null })).toMatch(/nicht bekannt/);
    });
    it("lässt nur ohne bekannten Jahrgang wählen", () => {
        expect(jahrgangWaehlbar({ jahrgang_quelle: null })).toBe(true);
        expect(jahrgangWaehlbar({ jahrgang_quelle: "gewaehlt" })).toBe(true);
        expect(jahrgangWaehlbar({ jahrgang_quelle: "festgelegt" })).toBe(false);
        expect(jahrgangWaehlbar({ jahrgang_quelle: "abgeleitet" })).toBe(false);
    });
});

describe("fachschaftHinweis", () => {
    it("nur bei Fachschaft mit Schüler:innen in der Zielgruppe", () => {
        expect(fachschaftHinweis({ scope: "subject_department", audience: "student" })).toMatch(/nicht/);
        expect(fachschaftHinweis({ scope: "subject_department", audience: "all" })).toMatch(/nicht/);
        expect(fachschaftHinweis({ scope: "subject_department", audience: "teacher" })).toBeNull();
        expect(fachschaftHinweis({ scope: "teaching_group", audience: "student" })).toBeNull();
    });
});
