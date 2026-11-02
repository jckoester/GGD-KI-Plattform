import { describe, it, expect } from "vitest";
import {
    budgetBalken,
    zuwachsText,
    zuwachsKurz,
    uebertragText,
    kostenAnzeige,
    kostenErklaerung,
    zuschlagText,
} from "./budget_text.js";
import { text as einheitenText } from "./einheiten.js";

describe("zuwachsText", () => {
    it("nennt Betrag und Termin", () => {
        const text = zuwachsText({
            wochenbetrag_eur: 0.04,
            naechste_aufstockung: "2026-09-21", // Montag
        });
        // Kein zweiter Punkt am Ende: „Mo., 21.09." bringt ihn schon mit.
        expect(text).toBe(
            `Jede Unterrichtswoche kommen ${einheitenText(400)} dazu — das nächste Mal am Mo., 21.09.`,
        );
        expect(text).not.toMatch(/\.\.$/);
    });

    it("sagt am Schuljahresende, dass nichts mehr kommt", () => {
        // Ohne Folgetermin wäre „wächst jede Woche" eine falsche Zusage.
        expect(zuwachsText({ wochenbetrag_eur: 0.04, naechste_aufstockung: null })).toBe(
            "Bis zum Schuljahresende kommt kein Guthaben mehr dazu.",
        );
    });

    it("schweigt, wenn die Angaben fehlen", () => {
        // Lieber nichts sagen als etwas Halbes — der Restbetrag steht daneben.
        expect(zuwachsText(null)).toBeNull();
        expect(zuwachsText({})).toBeNull();
        expect(zuwachsText({ wochenbetrag_eur: 0 })).toBeNull();
        expect(zuwachsText({ wochenbetrag_eur: null, naechste_aufstockung: "2026-09-21" }))
            .toBeNull();
    });

    it("hält ein kaputtes Datum aus", () => {
        expect(
            zuwachsText({ wochenbetrag_eur: 0.04, naechste_aufstockung: "kein-datum" }),
        ).toBe("Bis zum Schuljahresende kommt kein Guthaben mehr dazu.");
    });
});

describe("zuwachsKurz", () => {
    it("passt in die Seitenleiste", () => {
        expect(
            zuwachsKurz({ wochenbetrag_eur: 0.31, naechste_aufstockung: "2026-09-21" }),
        ).toBe(`+${einheitenText(3100)} am Mo., 21.09.`);
    });

    it("schweigt ohne Termin", () => {
        expect(zuwachsKurz({ wochenbetrag_eur: 0.31, naechste_aufstockung: null })).toBeNull();
        expect(zuwachsKurz({})).toBeNull();
    });
});

describe("uebertragText", () => {
    it("nennt Wochenzahl und Betrag statt „einige Wochen“", () => {
        expect(uebertragText({ wochenbetrag_eur: 0.04, vorsprung_wochen: 3 })).toBe(
            `Ungenutztes bleibt dir erhalten — bis zu ${einheitenText(1200)}, dem Betrag von 3 Wochen. ` +
                "Mehr sammelt sich nicht an.",
        );
    });

    it("beugt den Singular", () => {
        expect(uebertragText({ wochenbetrag_eur: 0.5, vorsprung_wochen: 1 })).toBe(
            `Ungenutztes bleibt dir erhalten — bis zu ${einheitenText(5000)}, dem Betrag von einer Woche. ` +
                "Mehr sammelt sich nicht an.",
        );
    });

    it("nennt ohne Wochenbetrag wenigstens die Wochen", () => {
        expect(uebertragText({ vorsprung_wochen: 3 })).toBe(
            "Ungenutztes bleibt dir erhalten, höchstens aber der Betrag von 3 Wochen.",
        );
    });

    it("schweigt ohne konfigurierten Vorsprung", () => {
        expect(uebertragText({ wochenbetrag_eur: 0.04 })).toBeNull();
        expect(uebertragText({ vorsprung_wochen: 0 })).toBeNull();
        expect(uebertragText(null)).toBeNull();
    });
});

describe("kostenAnzeige", () => {
    it("meldet den ausstehenden Zustand statt zu schweigen", () => {
        // Nichts anzuzeigen wäre von „hat nichts gekostet" nicht zu unterscheiden.
        expect(kostenAnzeige(null, "ausstehend")).toEqual({
            text: "Kosten werden ermittelt …",
            unsicher: true,
        });
    });

    it("meldet ausstehend auch dann, wenn schon ein Teilbetrag dasteht", () => {
        // Bildkosten sind sofort bekannt, die Textkosten noch nicht.
        expect(kostenAnzeige(einheitenText(4), "ausstehend").unsicher).toBe(true);
    });

    it("kennzeichnet eine Teilsumme als Untergrenze", () => {
        expect(kostenAnzeige(einheitenText(1), "unvollstaendig")).toEqual({
            text: `mindestens ${einheitenText(1)}`,
            unsicher: true,
        });
    });

    it("zeigt den belastbaren Betrag schlicht", () => {
        expect(kostenAnzeige(einheitenText(2), "vollstaendig")).toEqual({
            text: einheitenText(2),
            unsicher: false,
        });
    });

    it("behandelt fehlenden Zustand wie belastbar", () => {
        // Bestandszeilen vor Migration 0058 tragen `null` — für sie gab es die
        // Unterscheidung nicht, und eine Warnung wäre eine erfundene Aussage.
        expect(kostenAnzeige(einheitenText(2), null)).toEqual({ text: einheitenText(2), unsicher: false });
    });

    it("zeigt ohne Betrag und ohne Zustand gar nichts", () => {
        expect(kostenAnzeige(null, null)).toBeNull();
        expect(kostenAnzeige(undefined)).toBeNull();
    });
});

describe("kostenErklaerung", () => {
    it("erklärt beide unsicheren Zustände", () => {
        expect(kostenErklaerung("ausstehend")).toContain("Verzögerung");
        expect(kostenErklaerung("unvollstaendig")).toContain("höher");
    });

    it("erklärt nichts, wo es nichts zu erklären gibt", () => {
        expect(kostenErklaerung("vollstaendig")).toBeNull();
        expect(kostenErklaerung(null)).toBeNull();
    });
});


describe("zuschlagText", () => {
    it("nennt den Zuschlag in Einheiten und dass er mit dem Schuljahr endet", () => {
        // 0,55 USD / 1,1 × 10 000 = 5 000 Einheiten
        expect(zuschlagText({ zuschlag_usd: 0.55, eur_usd_rate: 1.1, einheiten_je_euro: 10000 }))
            .toBe(`Darin enthalten: ${einheitenText(5000)} als Zuschlag in diesem Schuljahr.`);
    });

    it("schweigt ohne Zuschlag", () => {
        expect(zuschlagText({ zuschlag_usd: 0, eur_usd_rate: 1.1 })).toBeNull();
        expect(zuschlagText({ zuschlag_usd: null, eur_usd_rate: 1.1 })).toBeNull();
        expect(zuschlagText({})).toBeNull();
    });

    it("schweigt ohne Kurs, statt eine falsche Zahl zu nennen", () => {
        expect(zuschlagText({ zuschlag_usd: 0.55 })).toBeNull();
    });
});

describe("budgetBalken", () => {
    // Wochenbetrag 1 €, drei Wochen Vorsprung, Kurs 1,1 → Höchststand 3,30 $.
    const basis = { wochenbetrag_eur: 1, vorsprung_wochen: 3, eur_usd_rate: 1.1 };

    it("ist voll, wer den Höchststand hat — egal, wie hoch die Jahresgrenze ist", () => {
        expect(budgetBalken({ ...basis, remaining_usd: 3.3, max_budget_usd: 30 }))
            .toEqual({ anteil: 100, knapp: false });
    });

    it("zeigt nach der Aufbuchung ein Drittel, wer alles verbraucht hatte", () => {
        // Bis 0.28.1: 1 von 8 Wochenbeträgen → 12 % in Rot.
        expect(budgetBalken({ ...basis, remaining_usd: 1.1, max_budget_usd: 8.8 }).anteil)
            .toBe(33);
    });

    it("deckelt bei 100 % — ein Zuschlag hebt den Rest über den Höchststand", () => {
        expect(budgetBalken({ ...basis, remaining_usd: 5.5 }).anteil).toBe(100);
    });

    it("wird knapp ab einem Fünftel und nie negativ", () => {
        expect(budgetBalken({ ...basis, remaining_usd: 0.66 }).knapp).toBe(true);
        expect(budgetBalken({ ...basis, remaining_usd: -0.1 }).anteil).toBe(0);
    });

    it("fällt ohne Wochenbetrag auf die Obergrenze zurück", () => {
        expect(budgetBalken({ remaining_usd: 2, max_budget_usd: 4 }).anteil).toBe(50);
        expect(budgetBalken({ remaining_usd: 2 })).toBe(null);
        expect(budgetBalken({})).toBe(null);
    });
});
