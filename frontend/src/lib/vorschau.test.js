import { describe, expect, it } from "vitest";
import {
    bandText, hinweisText, jahrgangFuerAssistent, kannVorschauBetreten, restMinuten,
    vorschauGruppen, zielNachEintritt,
} from "./vorschau.js";

describe("kannVorschauBetreten", () => {
    it("Lehrkräfte und Admins, nicht Schüler:innen und nicht aus einer Vorschau", () => {
        expect(kannVorschauBetreten({ roles: ["teacher"] })).toBe(true);
        expect(kannVorschauBetreten({ roles: ["teacher", "admin"] })).toBe(true);
        expect(kannVorschauBetreten({ roles: ["student"] })).toBe(false);
        expect(kannVorschauBetreten({ roles: ["student"], vorschau: { jahrgang: "9" } })).toBe(false);
        expect(kannVorschauBetreten(null)).toBe(false);
    });
});

describe("restMinuten", () => {
    it("rundet auf und wird nie negativ", () => {
        expect(restMinuten(1000 + 61, 1000 * 1000)).toBe(2);
        expect(restMinuten(1000 + 60, 1000 * 1000)).toBe(1);
        expect(restMinuten(900, 1000 * 1000)).toBe(0);
        expect(restMinuten(undefined)).toBe(null);
    });
});

describe("bandText", () => {
    it("nennt Klasse und Gruppe", () => {
        expect(bandText({ jahrgang: "9" }, "M9c"))
            .toBe("Du siehst die App als Schüler:in — Klasse 9, Gruppe M9c");
        expect(bandText({ jahrgang: "7" })).toBe("Du siehst die App als Schüler:in — Klasse 7");
        expect(bandText(null)).toBe("");
    });
});

describe("jahrgangFuerAssistent", () => {
    const stufen = [5, 6, 7, 8, 9, 10, 11, 12];
    it("nimmt die unterste Stufe des Assistenten, die es gibt", () => {
        expect(jahrgangFuerAssistent({ min_grade: 8, max_grade: 13 }, stufen)).toBe(8);
        expect(jahrgangFuerAssistent({ min_grade: 1, max_grade: 6 }, stufen)).toBe(5);
        expect(jahrgangFuerAssistent({ min_grade: null, max_grade: null }, stufen)).toBe(5);
        expect(jahrgangFuerAssistent({ min_grade: 13 }, stufen)).toBe(5);
    });
});

describe("vorschauGruppen", () => {
    it("nur aktuelle Unterrichtsgruppen", () => {
        const gruppen = [
            { id: 1, type: "teaching_group", aktuell: true },
            { id: 2, type: "teaching_group", aktuell: false },
            { id: 3, type: "subject_department", aktuell: true },
            { id: 4, type: "teaching_group" },
        ];
        expect(vorschauGruppen(gruppen).map((g) => g.id)).toEqual([1, 4]);
    });
});

describe("Ziel und Hinweis", () => {
    it("führt mit Assistent in den Chat", () => {
        expect(zielNachEintritt(12)).toBe("/chat?assistant_id=12");
        expect(zielNachEintritt(null)).toBe("/welcome");
    });
    it("unterscheidet Ablauf und Beenden", () => {
        expect(hinweisText("abgelaufen")).toMatch(/abgelaufen/);
        expect(hinweisText("beendet")).toMatch(/beendet/);
        expect(hinweisText("x")).toBe(null);
    });
});
