import { describe, it, expect } from "vitest";
import { chatFehlertext, istLeereAntwort, leereAntwortText } from "./chat_errors.js";
import { ApiError } from "./api.js";

describe("chatFehlertext", () => {
    it("zeigt den Satz des Backends, wenn es einen mitschickt", () => {
        const err = new ApiError(429, "Dein Budget für diesen Zeitraum ist aufgebraucht.");
        expect(chatFehlertext(err)).toBe(
            "Dein Budget für diesen Zeitraum ist aufgebraucht.",
        );
    });

    it("unterscheidet Drosselung von erschöpftem Budget", () => {
        // Beide kommen als 429. Bis 08/2026 stand hier eine feste Zuordnung
        // `429 → "Dein Budget ist erschöpft."`, die den Drosselungsfall verfälschte.
        const gedrosselt = new ApiError(429, "Zu viele Anfragen. Bitte kurz warten.");
        const budget = new ApiError(429, "Dein Budget ist aufgebraucht.");

        expect(chatFehlertext(gedrosselt)).toContain("Zu viele Anfragen");
        expect(chatFehlertext(gedrosselt)).not.toContain("Budget");
        expect(chatFehlertext(budget)).toContain("Budget");
    });

    it("setzt bei 502/503 einen lesbaren Satz ein", () => {
        // Dort schickt das Backend nur Technisches („LiteLLM Proxy nicht erreichbar").
        expect(chatFehlertext(new ApiError(502, "LiteLLM Proxy nicht erreichbar"))).toBe(
            "Der KI-Dienst ist gerade nicht erreichbar.",
        );
        expect(chatFehlertext(new ApiError(503, "irgendwas"))).toBe(
            "Der KI-Dienst ist vorübergehend nicht verfügbar.",
        );
    });

    it("fängt den Netzwerkabbruch (Status 0) ab", () => {
        expect(chatFehlertext(new ApiError(0, undefined))).toBe(
            "Verbindung zum Server fehlgeschlagen.",
        );
    });

    it("bleibt bei unbrauchbaren Eingaben verständlich", () => {
        const unbekannt = "Ein unbekannter Fehler ist aufgetreten.";
        expect(chatFehlertext(undefined)).toBe(unbekannt);
        expect(chatFehlertext({})).toBe(unbekannt);
        expect(chatFehlertext({ status: 418, message: "   " })).toBe(unbekannt);
    });

    it("reicht Fehler ohne bekannten Status durch", () => {
        expect(chatFehlertext(new ApiError(400, "Assistent nicht verfügbar"))).toBe(
            "Assistent nicht verfügbar",
        );
    });
});

describe("istLeereAntwort", () => {
    it("erkennt die fertige Antwort ohne Inhalt", () => {
        expect(istLeereAntwort({ content: "" }, false)).toBe(true);
        expect(istLeereAntwort({ content: null }, false)).toBe(true);
    });

    it("hält eine Antwort mit Text nicht für leer", () => {
        expect(istLeereAntwort({ content: "Hallo" }, false)).toBe(false);
    });

    it("hält eine Antwort mit Bild nicht für leer", () => {
        // Ein erzeugtes Bild ohne Begleittext ist eine Antwort — nur eben keine
        // aus Buchstaben. Ohne diesen Fall bekäme jedes Bild einen Fehlalarm.
        //
        // Seit die Bilder **in** der Blase sitzen (09.09.2026) trägt der Fall
        // doppelt: Er entscheidet auch, ob die Blase überhaupt gerendert wird.
        expect(istLeereAntwort({ content: "", images: [{ image_id: "x" }] }, false))
            .toBe(false);
    });

    it("meldet während des Streams nichts", () => {
        // Da ist der Inhalt nur noch nicht da.
        expect(istLeereAntwort({ content: "" }, true)).toBe(false);
    });

    it("verträgt eine fehlende Nachricht", () => {
        expect(istLeereAntwort(null, false)).toBe(false);
        expect(istLeereAntwort(undefined)).toBe(false);
    });
});

describe("leereAntwortText", () => {
    it("erklärt und schlägt das Wiederholen vor", () => {
        const text = leereAntwortText();
        expect(text).toContain("nichts geantwortet");
        expect(text).toContain("noch einmal");
    });

    it("nennt die Kosten, wenn welche gebucht wurden", () => {
        // Sie zu verschweigen wäre die zweite Hälfte desselben Fehlers.
        expect(leereAntwortText("0,01")).toContain("0,01 €");
        expect(leereAntwortText("0,01")).toContain("trotzdem berechnet");
    });

    it("erfindet keine Kosten, wenn keine bekannt sind", () => {
        expect(leereAntwortText(null)).not.toContain("€");
    });
});
