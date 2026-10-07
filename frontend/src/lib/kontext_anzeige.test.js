import { afterEach, describe, expect, it, vi } from "vitest";
import { kontextEintraege, kontextStufe, KONTEXT_VORGABE } from "./kontext_anzeige.js";
import { streamChat } from "./api.js";

const OXIDATION = {
    node_id: "n1",
    title: "Oxidation",
    content_type: "begriff",
    fach: "Chemie",
    herkunft: "vorab",
    aehnlichkeit: 0.616,
    updated_at: "2026-10-03T12:00:00Z",
};
const NAME = { ...OXIDATION, node_id: "n2", title: "Redoxreaktion", aehnlichkeit: null };
const WERKZEUG = {
    ...OXIDATION, node_id: "n3", title: "Stoffmenge", fach: null, herkunft: "werkzeug",
    aehnlichkeit: null, updated_at: null,
};

describe("kontextStufe", () => {
    it("nimmt die gespeicherte Stufe", () => {
        expect(kontextStufe({ kontext_anzeige: "aus" })).toBe("aus");
        expect(kontextStufe({ kontext_anzeige: "ausfuehrlich" })).toBe("ausfuehrlich");
    });

    it("fällt bei fehlendem oder unbekanntem Wert auf „kurz“ zurück", () => {
        expect(KONTEXT_VORGABE).toBe("kurz");
        expect(kontextStufe(undefined)).toBe("kurz");
        expect(kontextStufe({})).toBe("kurz");
        expect(kontextStufe({ kontext_anzeige: "alles" })).toBe("kurz");
    });
});

describe("kontextEintraege", () => {
    const antwort = { role: "assistant", kontext: [OXIDATION, NAME, WERKZEUG] };

    it("zeigt keine Zeile ohne Bausteine — weder leer noch als „Kontext (0)“", () => {
        expect(kontextEintraege({ role: "assistant" }, "kurz")).toBeNull();
        expect(kontextEintraege({ role: "assistant", kontext: [] }, "ausfuehrlich")).toBeNull();
    });

    it("zeigt nichts bei „aus“ und während des Streams", () => {
        expect(kontextEintraege(antwort, "aus")).toBeNull();
        expect(kontextEintraege(antwort, "kurz", true)).toBeNull();
    });

    it("hängt die Fassung eines Begriffs an den Titel — sonst stehen zwei gleich da", () => {
        const zwei = {
            kontext: [
                { ...OXIDATION, fassung: "Sauerstoffaufnahme" },
                { ...OXIDATION, node_id: "n9", fassung: "Elektronenabgabe" },
            ],
        };
        expect(kontextEintraege(zwei, "kurz").map((e) => e.titel)).toEqual([
            "Oxidation (Sauerstoffaufnahme)", "Oxidation (Elektronenabgabe)",
        ]);
    });

    it("Abbildungen nur ausführlich und nur bei Bausteinen, die welche haben", () => {
        const mit = { kontext: [{ ...OXIDATION, hat_abbildungen: true }, NAME] };
        expect(kontextEintraege(mit, "kurz").map((e) => e.abbildungen)).toEqual([false, false]);
        expect(kontextEintraege(mit, "ausfuehrlich").map((e) => e.abbildungen)).toEqual([
            true, false,
        ]);
    });

    it("der Link führt mit ?back= in den Chat zurück — Pfad und Query", () => {
        const [erster] = kontextEintraege(antwort, "kurz", false, "/chat?id=k-1");
        expect(erster.href).toBe("/knowledge/n1?back=%2Fchat%3Fid%3Dk-1");
        // Ohne Ziel (außerhalb des Chats) der schlichte Link.
        expect(kontextEintraege(antwort, "kurz")[0].href).toBe("/knowledge/n1");
    });

    it("die Chatseite gibt die Konversation als Rückweg mit", async () => {
        // ⚠️ Nicht `$page.url`: Ein neuer Chat steht dort als `/chat` ohne `?id=`.
        const { readFileSync } = await import("node:fs");
        const quelle = readFileSync(
            new URL("../routes/(app)/chat/+page.svelte", import.meta.url), "utf-8",
        );
        expect(quelle).toMatch(/kontextZurueck=\{conversationId \? `\/chat\?id=\$\{conversationId\}`/);
    });

    it("kurz: Titel, Fach und Link — keine Details", () => {
        const [erster, , dritter] = kontextEintraege(antwort, "kurz");
        expect(erster).toEqual({
            node_id: "n1", titel: "Oxidation", fach: "Chemie", href: "/knowledge/n1",
            details: [], abbildungen: false,
        });
        expect(dritter.fach).toBeNull();
    });

    it("ausführlich: Fundweg, Ähnlichkeit oder Name, Änderungsdatum", () => {
        const [erster, zweiter, dritter] = kontextEintraege(antwort, "ausfuehrlich");
        expect(erster.details).toEqual([
            "vorab zur Frage gefunden", "Ähnlichkeit 0,62", "geändert am 03.10.2026",
        ]);
        // Vorab ohne Ähnlichkeit = über den Namen gefunden.
        expect(zweiter.details).toEqual([
            "vorab zur Frage gefunden", "über den Namen", "geändert am 03.10.2026",
        ]);
        expect(dritter.details).toEqual(["vom Assistenten nachgeschlagen"]);
    });
});

// ── SSE: das Ereignis `kontext` ──────────────────────────────────────────────

function sseAntwort(teile) {
    const kodiert = teile.map((t) => new TextEncoder().encode(t));
    return {
        ok: true,
        status: 200,
        headers: new Map([["X-Conversation-Id", "konv-1"]]),
        body: {
            getReader: () => ({
                read: async () =>
                    kodiert.length
                        ? { done: false, value: kodiert.shift() }
                        : { done: true, value: undefined },
            }),
        },
    };
}

async function alles(gen) {
    const ergebnis = [];
    for await (const x of gen) ergebnis.push(x);
    return ergebnis;
}

afterEach(() => vi.restoreAllMocks());

describe("streamChat: Ereignis „kontext“", () => {
    it("liefert die Bausteine als eigenes Ereignis, nicht im Antworttext", async () => {
        const nutzlast = JSON.stringify({ bausteine: [OXIDATION] });
        global.fetch = vi.fn().mockResolvedValue(sseAntwort([
            'data: {"choices":[{"delta":{"content":"Hallo"}}]}\n\n',
            // über zwei Lesevorgänge verteilt — die Grenze ist die Leerzeile
            `event: kontext\ndata: ${nutzlast.slice(0, 20)}`,
            `${nutzlast.slice(20)}\n\n`,
            'event: message\ndata: {"message_id":"m1"}\n\n',
            "data: [DONE]\n\n",
        ]));

        const ereignisse = await alles(streamChat([{ role: "user", content: "x" }]));

        expect(ereignisse).toContainEqual({ type: "kontext", bausteine: [OXIDATION] });
        const text = ereignisse.filter((e) => typeof e === "string").join("");
        expect(text).toBe("Hallo");
        expect(ereignisse.at(-1)).toEqual({ type: "message", message_id: "m1" });
    });
});
