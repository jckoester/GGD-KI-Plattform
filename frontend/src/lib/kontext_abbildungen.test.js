// @vitest-environment jsdom
// Die Abbildungen in der Kontextliste (0.14, Schritt 4): laden erst beim Aufklappen,
// einmal je Knoten, und gesetzt von derselben Funktion wie in der Detailansicht —
// also sanitisiert. `zeigeAbbildungen` schreibt ins DOM, deshalb jsdom.
import { afterEach, describe, expect, it, vi } from "vitest";
import { SCHALTZEICHEN, alleAbbildungen } from "./abbildungen.js";
import { ladeAbbildungen, vergiss, zeigeAbbildungen } from "./kontext_anzeige.js";

const PFAD = '<path d="M 0 0 L 10 10"/>';
const SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">${PFAD}</svg>`;
const WASSER = { datei: "_Abb/EN_H2O.svg", beschreibung: "Wassermolekül", svg: SVG };

afterEach(() => vergiss());

describe("alleAbbildungen", () => {
    it("nimmt die Illustrationen und beim Bauteil das Schaltzeichen", () => {
        const bauteil = {
            content_type: "bauteil",
            metadata: { illustrationen: [WASSER], schaltzeichen: { svg: SVG, kennung: "R" } },
        };
        expect(alleAbbildungen(bauteil).map((a) => a.datei)).toEqual([
            "_Abb/EN_H2O.svg", SCHALTZEICHEN,
        ]);
    });

    it("kein Schaltzeichen außerhalb eines Bauteils, keine kaputten Angaben", () => {
        const begriff = {
            content_type: "begriff",
            metadata: { illustrationen: { kaputt: true }, schaltzeichen: { svg: SVG } },
        };
        expect(alleAbbildungen(begriff)).toEqual([]);
        expect(alleAbbildungen(null)).toEqual([]);
    });
});

describe("ladeAbbildungen", () => {
    it("holt jeden Knoten einmal und behält nur, was ein SVG hat", async () => {
        const holen = vi.fn().mockResolvedValue({
            content_type: "begriff",
            metadata: { illustrationen: [WASSER, { datei: "fehlt.svg" }] },
        });
        const erste = await ladeAbbildungen("n1", holen);
        const zweite = await ladeAbbildungen("n1", holen);
        expect(erste.map((a) => a.datei)).toEqual(["_Abb/EN_H2O.svg"]);
        expect(zweite).toBe(erste);
        expect(holen).toHaveBeenCalledTimes(1);
    });

    it("ein Fehler heißt „keine Abbildungen“ — und wird beim nächsten Mal neu versucht", async () => {
        const holen = vi.fn()
            .mockRejectedValueOnce(new Error("404"))
            .mockResolvedValueOnce({ content_type: "begriff", metadata: { illustrationen: [WASSER] } });
        expect(await ladeAbbildungen("n2", holen)).toEqual([]);
        expect((await ladeAbbildungen("n2", holen)).length).toBe(1);
        expect(holen).toHaveBeenCalledTimes(2);
    });
});

describe("zeigeAbbildungen", () => {
    it("setzt je Abbildung eine Hülle mit Bild und Beschreibung", () => {
        const wurzel = document.createElement("span");
        zeigeAbbildungen(wurzel, [WASSER]);
        const bild = wurzel.querySelector(".abbildung-block .abbildung-bild");
        expect(bild.getAttribute("aria-label")).toBe("Wassermolekül");
        // Die Zeichnung bleibt — die Falle aus Phase 17 strich das `d`-Attribut.
        expect(bild.querySelector("path").getAttribute("d")).toBe("M 0 0 L 10 10");
    });

    it("sanitisiert: <script> und Event-Handler fallen weg", () => {
        const boese = {
            datei: "boese.svg",
            svg: `<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><script>alert(2)</script>${PFAD}</svg>`,
        };
        const wurzel = document.createElement("span");
        zeigeAbbildungen(wurzel, [boese]);
        expect(wurzel.innerHTML).not.toContain("script");
        expect(wurzel.innerHTML).not.toContain("onload");
        expect(wurzel.querySelector("path")).not.toBeNull();
    });

    it("ersetzt beim zweiten Lauf, statt anzuhängen", () => {
        const wurzel = document.createElement("span");
        zeigeAbbildungen(wurzel, [WASSER]);
        zeigeAbbildungen(wurzel, [WASSER]);
        expect(wurzel.querySelectorAll(".abbildung-block").length).toBe(1);
        zeigeAbbildungen(wurzel, []);
        expect(wurzel.children.length).toBe(0);
    });
});
