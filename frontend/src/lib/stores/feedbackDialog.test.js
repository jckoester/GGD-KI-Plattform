/**
 * Der Schalter des Rückmelde-Dialogs (ADR-020, AP4).
 *
 * Klein, aber nicht überflüssig: Der Dialog hängt am Layout, geöffnet wird er
 * anderswo. Bliebe `chatAnhaengen` nach dem Schließen stehen, käme das Formular beim
 * nächsten Öffnen — etwa aus dem Nutzermenü auf einer ganz anderen Seite — mit einer
 * Vorauswahl hoch, die dort niemand gesetzt hat.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { get } from "svelte/store";
import {
    feedbackDialog,
    oeffneFeedback,
    schliesseFeedback,
} from "./feedbackDialog.js";

beforeEach(schliesseFeedback);

describe("feedbackDialog", () => {
    it("ist anfangs zu", () => {
        expect(get(feedbackDialog).offen).toBe(false);
    });

    it("öffnet ohne Vorauswahl", () => {
        oeffneFeedback();
        expect(get(feedbackDialog)).toEqual({ offen: true, chatAnhaengen: false });
    });

    it("öffnet mit vorgewähltem Chat", () => {
        oeffneFeedback({ chatAnhaengen: true });
        expect(get(feedbackDialog).chatAnhaengen).toBe(true);
    });

    it("vergisst die Vorauswahl beim Schließen", () => {
        oeffneFeedback({ chatAnhaengen: true });
        schliesseFeedback();
        oeffneFeedback();
        expect(get(feedbackDialog).chatAnhaengen).toBe(false);
    });
});
