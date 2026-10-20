import { afterEach, describe, expect, it, vi } from "vitest";
import { legeSlotZusammen, teileSlot } from "./api.js";

afterEach(() => vi.restoreAllMocks());

function antwort(status, body) {
    return { ok: status < 400, status, json: async () => body };
}

describe("Doppelstunde teilen (0.19)", () => {
    it("schickt den gelesenen Stand mit", async () => {
        global.fetch = vi.fn().mockResolvedValue(antwort(200, { slots: [] }));
        await teileSlot("s-1", "2026-10-20T08:00:00Z");
        const [url, init] = global.fetch.mock.calls[0];
        expect(url).toMatch(/\/planning\/slots\/s-1\/teilen$/);
        expect(init.method).toBe("POST");
        expect(JSON.parse(init.body)).toEqual({ expected_updated_at: "2026-10-20T08:00:00Z" });
    });

    it("reicht die Begründung einer Weigerung durch", async () => {
        global.fetch = vi.fn().mockResolvedValue(
            antwort(409, { detail: "Die 4. Stunde trägt eigenen Inhalt." }));
        await expect(legeSlotZusammen("s-2")).rejects.toThrow("Die 4. Stunde trägt eigenen Inhalt.");
        expect(global.fetch.mock.calls[0][0]).toMatch(/\/planning\/slots\/s-2\/zusammenlegen$/);
    });
});
