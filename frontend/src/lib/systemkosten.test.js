import { describe, it, expect } from "vitest";
import { systemText } from "./systemkosten.js";

describe("systemkosten", () => {
    it("nennt Betrag und Anfragen", () => {
        expect(systemText(0.0012, 1234)).toBe("0,0012 € in 1.234 Anfragen");
    });

    it("zeigt einen winzigen Betrag nicht als null", () => {
        expect(systemText(0.00000014, 1)).toBe("< 0,0001 € in 1 Anfrage");
    });

    it("sagt, wenn es nichts gab", () => {
        expect(systemText(0, 0)).toBe("keine Anfragen");
    });
});
