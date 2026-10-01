import { describe, it, expect } from "vitest";
import {
    kostenMarke,
    eintragsText,
    angaben,
    tokenKurz,
    MARKE_KOSTEN,
    MARKE_WERKZEUGE,
} from "./modellangaben.js";
import { BEZEICHNUNG } from "./einheiten.js";

const KURS = 1.1705;
const FAKTOR = 10000;

// `chat-standard`: 0,000877 USD je Median-Nachricht → 7,49, gerundet 7 Einheiten.
const standard = {
    id: "chat-standard",
    usd_je_nachricht: 0.000877,
    kontextfenster: 128000,
    supports_function_calling: true,
};

describe("kostenMarke", () => {
    it("nennt mit der Münze, wovon die Zahl spricht", () => {
        // „~7" allein sagte nicht, wovon sieben (Jan, 01.10.2026). Das Einheitenwort
        // auszuschreiben macht den Eintrag zu lang — die Münze trägt die Bedeutung.
        expect(kostenMarke(standard, KURS, FAKTOR)).toBe(`~7 ${MARKE_KOSTEN}`);
    });

    it("schweigt, wenn kein Preis bekannt ist", () => {
        // Eine Null hieße „kostenlos" — und fehlende Preise meldet
        // check_litellm_config.py als Fehler, nicht die Oberfläche.
        expect(kostenMarke({ id: "x" }, KURS, FAKTOR)).toBeNull();
        expect(kostenMarke(standard, null, FAKTOR)).toBeNull();
    });
});

describe("eintragsText", () => {
    it("hängt Kostenmarke und Zahnrad an den Namen", () => {
        expect(eintragsText(standard, KURS, FAKTOR)).toBe(
            `chat-standard · ~7 ${MARKE_KOSTEN} · ${MARKE_WERKZEUGE}`,
        );
    });

    it("zeigt das Zahnrad nur bei belegten Werkzeugen", () => {
        // Es ist im Chat-Wähler der einzige Fähigkeitshinweis — dort gibt es keine
        // Angabenzeile darunter. Unbekannt heißt weglassen, nicht verneinen.
        const ohne = { id: "x", usd_je_nachricht: 0.000877 };
        expect(eintragsText(ohne, KURS, FAKTOR)).toBe(`x · ~7 ${MARKE_KOSTEN}`);
        expect(
            eintragsText({ ...ohne, supports_function_calling: false }, KURS, FAKTOR),
        ).toBe(`x · ~7 ${MARKE_KOSTEN}`);
    });

    it("bleibt der blanke Name, wenn nichts bekannt ist", () => {
        expect(eintragsText({ id: "chat-standard" }, KURS, FAKTOR)).toBe("chat-standard");
    });
});

describe("angaben", () => {
    it("nennt Kosten, Kontextfenster und Werkzeuge", () => {
        const liste = angaben(standard, KURS, FAKTOR);
        expect(liste.map((a) => a.was)).toEqual(["Kosten", "Kontextfenster", "Werkzeuge"]);
        expect(liste[0].wert).toBe(`etwa 7 ${BEZEICHNUNG.plural} je Nachricht`);
    });

    it("lässt Unbekanntes weg, statt es zu verneinen", () => {
        // ⚠️ Der Regelfall bei IONOS: Kontextfenster unbekannt. „0 Token" oder
        // „kann keine Werkzeuge" wäre eine erfundene Auskunft.
        const ionos = { id: "ionos-gpt-oss-120b", usd_je_nachricht: 0.000877 };
        expect(angaben(ionos, KURS, FAKTOR).map((a) => a.was)).toEqual(["Kosten"]);
    });

    it("nennt ein belegtes Nein bei den Werkzeugen", () => {
        // Hier ist das Nein wichtig: Ohne Werkzeuge fallen Wissensspeicher und
        // Unterrichtsplanung aus.
        const ohne = { id: "x", supports_function_calling: false };
        expect(angaben(ohne, KURS, FAKTOR)).toEqual([{ was: "Werkzeuge", wert: "nein" }]);
    });

    it("nennt weitere Fähigkeiten nur, wenn sie zutreffen", () => {
        const viel = { id: "x", denkt: true, bilder: true };
        expect(angaben(viel, KURS, FAKTOR).map((a) => a.was)).toEqual([
            "Denkt vor der Antwort",
            "Versteht Bilder",
        ]);
        expect(angaben({ id: "x", denkt: false, bilder: false }, KURS, FAKTOR)).toEqual([]);
    });

    it("ohne Modell eine leere Liste", () => {
        expect(angaben(null, KURS, FAKTOR)).toEqual([]);
    });
});

describe("tokenKurz", () => {
    it("nennt Token und eine vorstellbare Seitenzahl", () => {
        expect(tokenKurz(128000)).toBe("128.000 Token (ca. 190 Seiten)");
    });

    it("lässt die Seitenzahl weg, wenn sie unter einer Seite läge", () => {
        // 500 Token sind 0,74 Seiten — gerundet „1", und das wäre falsch.
        expect(tokenKurz(500)).toBe("500 Token");
    });

    it("beugt den Singular", () => {
        expect(tokenKurz(700)).toBe("700 Token (ca. 1 Seite)");
    });

    it("schweigt ohne Angabe", () => {
        expect(tokenKurz(null)).toBeNull();
        expect(tokenKurz(0)).toBeNull();
    });
});
