import { describe, it, expect } from "vitest";
import { zuwachsText, zuwachsKurz, uebertragText, kostenAnzeige, kostenErklaerung } from "./budget_text.js";

describe("zuwachsText", () => {
    it("nennt Betrag und Termin", () => {
        const text = zuwachsText({
            wochenbetrag_eur: 0.04,
            naechste_aufstockung: "2026-09-21", // Montag
        });
        // Kein zweiter Punkt am Ende: „Mo., 21.09." bringt ihn schon mit.
        expect(text).toBe(
            "Jede Unterrichtswoche kommen 0,04 € dazu — das nächste Mal am Mo., 21.09.",
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
        ).toBe("+0,31 € am Mo., 21.09.");
    });

    it("schweigt ohne Termin", () => {
        expect(zuwachsKurz({ wochenbetrag_eur: 0.31, naechste_aufstockung: null })).toBeNull();
        expect(zuwachsKurz({})).toBeNull();
    });
});

describe("uebertragText", () => {
    it("nennt Wochenzahl und Betrag statt „einige Wochen“", () => {
        expect(uebertragText({ wochenbetrag_eur: 0.04, vorsprung_wochen: 3 })).toBe(
            "Ungenutztes bleibt dir erhalten — bis zu 0,12 €, dem Betrag von 3 Wochen. " +
                "Mehr sammelt sich nicht an.",
        );
    });

    it("beugt den Singular", () => {
        expect(uebertragText({ wochenbetrag_eur: 0.5, vorsprung_wochen: 1 })).toBe(
            "Ungenutztes bleibt dir erhalten — bis zu 0,50 €, dem Betrag von einer Woche. " +
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
        expect(kostenAnzeige("0,04", "ausstehend").unsicher).toBe(true);
    });

    it("kennzeichnet eine Teilsumme als Untergrenze", () => {
        expect(kostenAnzeige("0,01", "unvollstaendig")).toEqual({
            text: "mindestens 0,01 €",
            unsicher: true,
        });
    });

    it("zeigt den belastbaren Betrag schlicht", () => {
        expect(kostenAnzeige("0,02", "vollstaendig")).toEqual({
            text: "0,02 €",
            unsicher: false,
        });
    });

    it("behandelt fehlenden Zustand wie belastbar", () => {
        // Bestandszeilen vor Migration 0058 tragen `null` — für sie gab es die
        // Unterscheidung nicht, und eine Warnung wäre eine erfundene Aussage.
        expect(kostenAnzeige("0,02", null)).toEqual({ text: "0,02 €", unsicher: false });
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
