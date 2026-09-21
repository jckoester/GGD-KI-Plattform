/**
 * Wächter über das, was nur im Markup steht (ADR-020, AP4).
 *
 * ⚠️ **Warum Quelltext statt Verhalten.** Das Projekt hat keine
 * Svelte-Komponententests; eine Komponente zu mounten verlangte
 * `@testing-library/svelte`, und jede neue Abhängigkeit trägt hier eine Obergrenze
 * (Sicherheits-Audit #17). Dieselbe Begründung wie in `picker_tastatur.test.js`.
 *
 * Geprüft wird deshalb, was sich am Quelltext ehrlich prüfen lässt: dass die drei
 * Pflichthinweise aus ADR-020 dastehen, dass die Chat-Auswahl an eine offene
 * Konversation gebunden ist — und dass die Chat-Seite den Assistenten-Store überall
 * dort pflegt, wo sie die Konversations-ID pflegt.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const lies = (p) => readFileSync(join(SRC, p), "utf-8");

const DIALOG = lies("lib/components/FeedbackDialog.svelte");
const CHAT = lies("routes/(app)/chat/+page.svelte");
const MENUE = lies("lib/components/UserMenu.svelte");

describe("Pflichthinweise des Formulars", () => {
    // ADR-020: Der Freitext ist die einzige Stelle im System, an der jemand
    // ungefiltert über Dritte schreiben kann. Der Hinweis ist Bedingung dafür,
    // dass es das Feld überhaupt gibt — nicht Zierde.
    it("warnt vor Namen Dritter und nennt, wer mitliest", () => {
        expect(DIALOG).toContain("Bitte keine Namen anderer Personen nennen.");
        expect(DIALOG).toContain("sehen nur die Administrator:innen der Schule");
    });

    it("benennt die verlängerte Aufbewahrung des Chat-Anhangs", () => {
        // Die Opt-in-Zusage: Der Snapshot überlebt die 90-Tage-Frist der Chats.
        expect(DIALOG).toContain(
            "Der Chat wird zusammen mit der Meldung gespeichert und mit ihr\n",
        );
        expect(DIALOG).toContain("gelöscht.");
    });

    it("sagt am Kontaktfeld, dass es freiwillig ist", () => {
        // Ohne den Satz liest sich ein leeres Eingabefeld wie eine Erwartung.
        expect(DIALOG).toContain("Freiwillig.");
        expect(DIALOG).toContain("persönlich ansprechen");
    });
});

describe("Chat-Anhang", () => {
    it("wird nur angeboten, wenn eine Konversation offen ist", () => {
        // Eine Auswahl ohne Wirkung wäre eine Zusage, die das Formular nicht hält.
        const ab = DIALOG.indexOf("{#if chatVorhanden}");
        expect(ab).toBeGreaterThan(-1);
        const bis = DIALOG.indexOf("{/if}", ab);
        expect(DIALOG.slice(ab, bis)).toContain("bind:checked={chatAnhaengen}");
    });

    it("hängt beim Absenden nur eine eigene, offene Konversation an", () => {
        expect(DIALOG).toContain("chatAnhaengen && chatVorhanden ? $activeConversationId : null");
    });
});

describe("Absende-Sperre", () => {
    it("hängt am Modul, nicht an einer zweiten Rechnung im Bauteil", () => {
        expect(DIALOG).toContain("istAbsendbar(text)");
        expect(DIALOG).toContain("disabled={!absendbar}");
    });
});

describe("Der Assistenten-Store folgt der Konversations-ID", () => {
    /**
     * Beide Stores beschreiben dieselbe Sache. Läuft einer dem anderen hinterher,
     * schickt eine Meldung aus dem Chat die Assistenten-ID einer **anderen**
     * Konversation mit — und niemand merkt es, weil die Angabe technisch aussieht.
     */
    const zeilenMit = (name) =>
        CHAT.split("\n").filter((z) => z.includes(`${name}.set(`)).length;

    it("wird genauso oft geschrieben wie die ID", () => {
        expect(zeilenMit("activeConversationAssistantId")).toBe(
            zeilenMit("activeConversationId"),
        );
    });

    it("wird an jeder Stelle mitgeleert, an der die ID geleert wird", () => {
        // Die schärfere Prüfung: nicht „gleich oft", sondern „an denselben Stellen".
        const stellen = [...CHAT.matchAll(/activeConversationId\.set\(null\)/g)];
        expect(stellen.length).toBeGreaterThanOrEqual(4);
        for (const treffer of stellen) {
            expect(CHAT.slice(treffer.index, treffer.index + 160)).toContain(
                "activeConversationAssistantId.set(null)",
            );
        }
    });
});

describe("Einstieg im Nutzermenü", () => {
    it("steht außerhalb jedes Rollen-Blocks", () => {
        // ADR-020: Der Einstieg liegt im Nutzermenü und nicht in der Sidebar, damit
        // er auf **jeder** Darstellungsstufe sichtbar ist. Stünde er in einem
        // Rollen-Block, wäre genau das verloren.
        const eintrag = MENUE.indexOf("Feedback geben");
        expect(eintrag).toBeGreaterThan(-1);
        const letzterRollenBlock = MENUE.lastIndexOf("{#if $user?.roles", eintrag);
        const abschluss = MENUE.indexOf("{/if}", letzterRollenBlock);
        // ⚠️ Ohne diese Zeile ist der Test wertlos: Wird der Eintrag in einen
        // Rollen-Block verschoben, findet `indexOf` gar kein `{/if}` mehr und gibt
        // `-1` zurück — und `-1 < eintrag` trifft immer zu. Beim Gegenprüfen kam der
        // Test deshalb grün zurück, obwohl der Einstieg nur noch Admins sahen.
        expect(abschluss).toBeGreaterThan(-1);
        expect(abschluss).toBeLessThan(eintrag);
    });

    it("führt zu „Meine Meldungen“", () => {
        expect(MENUE).toContain('href="/feedback"');
    });
});
