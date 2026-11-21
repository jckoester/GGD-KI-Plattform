import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChat } from "./api.js";

// Muster wie `api.bezug.test.js`.
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

describe("streamChat: Ereignis „modell_hinweis“ (0.51)", () => {
    it("meldet Grund und tatsächliches Modell, der Text bleibt unberührt", async () => {
        global.fetch = vi.fn().mockResolvedValue(sseAntwort([
            'event: modell_hinweis\ndata: {"detail":"Dein bevorzugtes Modell ist nicht mehr freigeschaltet.","modell":"chat-komplex"}\n\n',
            'data: {"choices":[{"delta":{"content":"Hallo."}}]}\n\n',
            "data: [DONE]\n\n",
        ]));
        const ereignisse = await alles(streamChat([{ role: "user", content: "x" }]));
        expect(ereignisse).toContainEqual({
            type: "modell_hinweis",
            detail: "Dein bevorzugtes Modell ist nicht mehr freigeschaltet.",
            modell: "chat-komplex",
        });
        expect(ereignisse.filter((e) => typeof e === "string").join("")).toBe("Hallo.");
    });

    it("ohne Modellangabe: null; kaputte Daten werden übergangen", async () => {
        global.fetch = vi.fn().mockResolvedValue(sseAntwort([
            'event: modell_hinweis\ndata: {"detail":"Grund"}\n\n',
            "event: modell_hinweis\ndata: {kaputt\n\n",
            'data: {"choices":[{"delta":{"content":"Weiter."}}]}\n\n',
            "data: [DONE]\n\n",
        ]));
        const ereignisse = await alles(streamChat([{ role: "user", content: "x" }]));
        expect(ereignisse.filter((e) => e?.type === "modell_hinweis")).toEqual([
            { type: "modell_hinweis", detail: "Grund", modell: null },
        ]);
        expect(ereignisse.filter((e) => typeof e === "string").join("")).toBe("Weiter.");
    });
});
