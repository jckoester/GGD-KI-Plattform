/**
 * Die Regeln des Rückmelde-Formulars (ADR-020, AP4).
 *
 * Was hier geprüft wird, steht bewusst **nicht** im Bauteil: Das Projekt hat keine
 * Svelte-Komponententests (Begründung in `picker_tastatur.test.js`), also liegt alles
 * Prüfbare in `feedback.js`. Das Bauteil rendert nur noch.
 */
import { describe, it, expect } from "vitest";
import {
    KATEGORIEN,
    MAX_LAENGE,
    MIN_LAENGE,
    baueNutzlast,
    fehlendeZeichen,
    feedbackFehlertext,
    istAbsendbar,
    kategorieText,
    sammleKontext,
    statusText,
} from "./feedback.js";

describe("Längen", () => {
    it("sperrt unter der Mindestlänge", () => {
        expect(istAbsendbar("kaputt")).toBe(false);
        expect(fehlendeZeichen("kaputt")).toBe(MIN_LAENGE - 6);
    });

    it("zählt Leerzeichen nicht mit", () => {
        // Sonst käme „test" mit angehängten Leerzeichen durch — genau wie im Backend.
        expect(istAbsendbar("test" + " ".repeat(40))).toBe(false);
    });

    it("gibt an der Grenze frei", () => {
        expect(istAbsendbar("x".repeat(MIN_LAENGE))).toBe(true);
        expect(fehlendeZeichen("x".repeat(MIN_LAENGE))).toBe(0);
    });

    it("sperrt über der Höchstlänge", () => {
        expect(istAbsendbar("x".repeat(MAX_LAENGE + 1))).toBe(false);
    });
});

describe("Kontext", () => {
    const kontext = () =>
        sammleKontext({
            pfad: "/knowledge/search?q=Krankheit+von+Mia",
            assistentId: 7,
            version: "0.10.3",
            kennung: "Mozilla/5.0",
            fenster: "375x812",
        });

    it("sammelt die fünf technischen Angaben", () => {
        expect(kontext()).toEqual({
            app_version: "0.10.3",
            route: "/knowledge/search",
            assistant_id: 7,
            user_agent: "Mozilla/5.0",
            viewport: "375x812",
        });
    });

    it("lässt die Query draußen", () => {
        // Sie kann tragen, was in einer Meldung nichts zu suchen hat.
        expect(kontext().route).not.toContain("Mia");
    });

    it("lässt auch das Fragment draußen", () => {
        expect(sammleKontext({ pfad: "/help/chat#mathe" }).route).toBe("/help/chat");
    });

    it("kommt ohne jede Angabe aus", () => {
        // Ein fehlender Kontext darf keine Meldung verhindern.
        expect(sammleKontext().app_version).toBe("unbekannt");
        expect(sammleKontext().route).toBe(null);
    });
});

describe("Nutzlast", () => {
    const basis = { kategorie: "bug", text: "  Der Knopf reagiert nicht mehr.  " };

    it("entrandet den Text", () => {
        expect(baueNutzlast(basis).content).toBe("Der Knopf reagiert nicht mehr.");
    });

    it("macht aus einem leeren Kontaktfeld NULL", () => {
        // `""` sähe für die Sichtung aus wie eine Angabe.
        expect(baueNutzlast({ ...basis, kontakt: "   " }).contact).toBe(null);
    });

    it("hängt den Chat nur an, wenn eine ID mitkommt", () => {
        expect(baueNutzlast(basis).attach_conversation_id).toBe(null);
        expect(baueNutzlast({ ...basis, chatId: "abc" }).attach_conversation_id).toBe("abc");
    });

    it("übernimmt den Kontext unverändert", () => {
        const kontext = { app_version: "0.10.3", route: "/chat" };
        expect(baueNutzlast({ ...basis, kontext })).toMatchObject(kontext);
    });

    it("trägt keine Felder, die der Server nicht kennt", () => {
        // Die Gegenprobe zur Datensparsamkeit: Wer hier etwas ergänzt, muss es
        // begründen — der Server wiese es ohnehin ab.
        expect(Object.keys(baueNutzlast(basis)).sort()).toEqual([
            "attach_conversation_id",
            "category",
            "contact",
            "content",
        ]);
    });
});

describe("Beschriftungen", () => {
    it("nennt die Version bei erledigten Meldungen", () => {
        expect(statusText({ status: "done", resolved_in_version: "0.10.4" })).toBe(
            "Erledigt in 0.10.4",
        );
    });

    it("kommt ohne Version aus", () => {
        expect(statusText({ status: "done" })).toBe("Erledigt");
    });

    it("zeigt Spam als „nicht umgesetzt“", () => {
        // Der Server maskiert das bereits; käme die Marke doch durch, bliebe die
        // Anzeige trotzdem richtig.
        expect(statusText({ status: "spam" })).toBe("Nicht umgesetzt");
    });

    it("kennt die drei Kategorien aus ADR-020", () => {
        expect(KATEGORIEN.map((k) => k.wert)).toEqual(["bug", "suggestion", "other"]);
        expect(kategorieText("suggestion")).toBe("Verbesserungsvorschlag");
    });
});

describe("Fehlertexte", () => {
    it("nimmt den Satz des Backends", () => {
        // Sperre und Limit schicken das einzige, was über die Dauer Auskunft gibt.
        const err = { status: 403, message: "Feedback vorübergehend gesperrt bis 04.10.2026." };
        expect(feedbackFehlertext(err)).toContain("04.10.2026");
    });

    it("hat einen Satz für den Fall ohne Auskunft", () => {
        expect(feedbackFehlertext({ status: 0 })).toBe("Die Meldung konnte nicht gesendet werden.");
    });
});
