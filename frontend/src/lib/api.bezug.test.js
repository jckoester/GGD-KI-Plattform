import { afterEach, describe, expect, it, vi } from "vitest";
import { streamChat } from "./api.js";

// Dasselbe Muster wie `kontext_anzeige.test.js` (Ereignis `kontext`).
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

describe("streamChat: Ereignis „bezug“ (0.15)", () => {
    it("meldet Gruppe, Fach und Stunde, die ein Werkzeug gesetzt hat", async () => {
        global.fetch = vi.fn().mockResolvedValue(sseAntwort([
            'event: tool_status\ndata: {"tool":"waehle_stunde","round":1}\n\n',
            'event: bezug\ndata: {"group_id":7,"subject_id":6,"stunde_node_id":"s-1"}\n\n',
            'data: {"choices":[{"delta":{"content":"Gefunden."}}]}\n\n',
            "data: [DONE]\n\n",
        ]));

        const ereignisse = await alles(streamChat([{ role: "user", content: "x" }]));

        expect(ereignisse).toContainEqual({ type: "bezug", groupId: 7, subjectId: 6, stundeId: "s-1" });
        expect(ereignisse.filter((e) => typeof e === "string").join("")).toBe("Gefunden.");
    });

    it("schickt den Stundenbezug nur für eine neue Konversation mit", async () => {
        global.fetch = vi.fn().mockResolvedValue(sseAntwort(["data: [DONE]\n\n"]));
        await alles(streamChat([{ role: "user", content: "x" }], null, null, 5, false, null, 7, "s-1"));
        expect(JSON.parse(global.fetch.mock.calls[0][1].body).stunde_node_id).toBe("s-1");

        await alles(streamChat([{ role: "user", content: "x" }], "konv-1", null, 5, false, null, 7, "s-1"));
        expect(JSON.parse(global.fetch.mock.calls[1][1].body).stunde_node_id).toBeUndefined();
    });
});
