import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, streamChat } from "./api.js";
import { chatFehlertext } from "./chat_errors.js";

// Dasselbe Muster wie `api.bezug.test.js`.
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

const MELDUNG = "Der KI-Dienst hat zu lange nicht geantwortet. Schick die Nachricht bitte noch einmal ab.";

afterEach(() => vi.restoreAllMocks());

describe("streamChat: Ereignis „fehler“ (abgerissener Strom, 0.15)", () => {
    it("liefert Text und Nachrichten-ID, dann wirft es die Meldung des Backends", async () => {
        global.fetch = vi.fn().mockResolvedValue(sseAntwort([
            'data: {"choices":[{"delta":{"content":"Ein Teil"}}]}\n\n',
            'event: message\ndata: {"message_id":"m-1"}\n\n',
            `event: fehler\ndata: ${JSON.stringify({ detail: MELDUNG })}\n\n`,
            "data: [DONE]\n\n",
        ]));

        const erhalten = [];
        let fehler;
        try {
            for await (const x of streamChat([{ role: "user", content: "x" }])) erhalten.push(x);
        } catch (e) {
            fehler = e;
        }

        expect(erhalten).toContain("Ein Teil");
        expect(erhalten).toContainEqual({ type: "message", message_id: "m-1" });
        expect(fehler).toBeInstanceOf(ApiError);
        expect(fehler.status).toBe(504);
        // In der Fehlerblase steht der Satz des Backends, kein fester Ersatz.
        expect(chatFehlertext(fehler)).toBe(MELDUNG);
    });
});
