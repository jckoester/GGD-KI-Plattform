import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, legeEigenenStundenassistentenAn } from "./api.js";

afterEach(() => vi.restoreAllMocks());

describe("legeEigenenStundenassistentenAn (0.15, Plan Schritt 7)", () => {
    it("schickt POST an den Endpunkt und liefert den neuen Assistenten", async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: true, status: 201, json: async () => ({ id: 42, name: "Mein Stundenassistent 1" }),
        });
        expect((await legeEigenenStundenassistentenAn()).id).toBe(42);
        const [url, optionen] = global.fetch.mock.calls[0];
        expect(url).toMatch(/\/assistants\/eigener-stundenassistent$/);
        expect(optionen.method).toBe("POST");
        expect(JSON.parse(optionen.body)).toEqual({ subject_id: null });
    });

    it("schickt das Fach mit, wenn eins übergeben wird", async () => {
        global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: 43 }) });
        await legeEigenenStundenassistentenAn({ subjectId: 7 });
        expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({ subject_id: 7 });
    });

    it("ohne schulweiten: der Satz des Backends", async () => {
        const detail = "Es ist kein schulweiter Stundenassistent eingerichtet, der als Vorlage dienen kann.";
        global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail }) });
        const fehler = await legeEigenenStundenassistentenAn().catch((e) => e);
        expect(fehler).toBeInstanceOf(ApiError);
        expect(fehler.message).toBe(detail);
    });
});
