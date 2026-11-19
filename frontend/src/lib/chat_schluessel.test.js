/** Schlüssel für Listen mit Zustand je Zeile (0.49, H3, F7 a: selektiv). */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { blasenSchluessel, mitSchluessel } from "./chat_schluessel.js";

const SRC = dirname(dirname(fileURLToPath(import.meta.url)));
const lies = (...t) => readFileSync(join(SRC, ...t), "utf8");

describe("mitSchluessel", () => {
    it("gespeicherte Nachricht: aus der Kennung; neue: laufend und eindeutig", () => {
        expect(mitSchluessel({ id: 7, role: "user" }).schluessel).toBe("m7");
        const a = mitSchluessel({ role: "assistant" });
        const b = mitSchluessel({ role: "assistant" });
        expect(a.schluessel).toMatch(/^n\d+$/);
        expect(a.schluessel).not.toBe(b.schluessel);
    });

    it("bleibt, wenn die Kennung später kommt (Ende des Streams) — keine neue Blase", () => {
        const neu = mitSchluessel({ role: "assistant", content: "" });
        const fertig = mitSchluessel({ ...neu, id: 99 });
        expect(fertig.schluessel).toBe(neu.schluessel);
    });
});

describe("blasenSchluessel", () => {
    it("Rückfall auf die Position in eigenem Namensraum", () => {
        expect(blasenSchluessel({ schluessel: "m1" }, 0)).toBe("m1");
        expect(blasenSchluessel({}, 3)).toBe("i3");
    });
});

describe("Chat-Seite", () => {
    const SEITE = lies("routes", "(app)", "chat", "+page.svelte");

    it("Blasen mit Schlüssel", () => {
        expect(SEITE).toContain("{#each messages as message, i (blasenSchluessel(message, i))}");
    });

    it("jede Stelle, die eine Nachricht anlegt, vergibt den Schlüssel", () => {
        // Neue Nachrichten-Objekte entstehen als Literal mit `role:` — außer in Spreads
        // (`{ ...m, … }`), die den Schlüssel mitnehmen.
        // `insertSeparators` legt Trenner beim Laden an; ihr Ergebnis geht als Ganzes durch
        // `mitSchluessel` (letzte Prüfung unten) und zählt hier nicht mit.
        const start = SEITE.indexOf("function insertSeparators(");
        const ende = SEITE.indexOf("\n    }\n", start);
        expect(start).toBeGreaterThan(0);
        const rest = SEITE.slice(0, start) + SEITE.slice(ende);
        const literale = rest.match(/\{\s*role:\s*"(user|assistant|error|change)"/g) ?? [];
        const mitS = rest.match(/mitSchluessel\(\{\s*role:\s*"(user|assistant|error|change)"/g) ?? [];
        expect(literale.length).toBeGreaterThan(0);
        expect(mitS.length).toBe(literale.length);
        expect(SEITE).toContain("insertSeparators(rawMessages).map(mitSchluessel)");
    });
});

describe("Letzte Chats", () => {
    const SEITE = lies("routes", "(app)", "history", "+page.svelte");

    it("Zeilen mit Schlüssel, Nachladen ohne Doppelte", () => {
        expect(SEITE).toContain("{#each conversations as conv (conv.id)}");
        expect(SEITE).toContain("data.items.filter((c) => !bekannt.has(c.id))");
    });
});
