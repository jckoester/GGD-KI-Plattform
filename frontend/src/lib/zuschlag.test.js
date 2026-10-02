import { describe, it, expect } from "vitest";
import {
    kennung,
    vorschauText,
    ergebnisText,
    KENNUNG_LAENGE,
    anfrage,
    schluessel,
    mitgliederVorgabe,
    eigeneKennung,
} from "./zuschlag.js";

describe("kennung", () => {
    it("zeigt die ersten zwölf Zeichen in Vierergruppen", () => {
        expect(kennung("a3f9c2b81e04" + "0".repeat(52))).toBe("a3f9 c2b8 1e04");
    });

    it("hat dieselbe Länge wie das Backend erwartet", () => {
        expect(KENNUNG_LAENGE).toBe(12);
    });

    it("schweigt ohne Pseudonym", () => {
        expect(kennung(null)).toBeNull();
        expect(kennung("kurz")).toBeNull();
    });
});

describe("vorschauText", () => {
    const basis = { ohne_rolle: 0, betrag_eur: 0.5, einheiten_je_person: 5000 };

    it("nennt Schüler:innen und Lehrkraft getrennt — die Falle bei Unterrichtsgruppen", () => {
        const t = vorschauText({ ...basis, anzahl: 29, schueler: 28, lehrkraefte: 1,
                                 summe_eur: 14.5, gruppenname: "7b" });
        expect(t).toContain("28 Schüler:innen, 1 Lehrkraft");
        expect(t).toContain("29 ×");
        expect(t).toMatch(/14,50\s€/);
        expect(t).toContain("5.000 Einheiten");
    });

    it("beugt den Singular", () => {
        const t = vorschauText({ ...basis, anzahl: 1, schueler: 0, lehrkraefte: 1, summe_eur: 0.5 });
        expect(t).toContain("1 Lehrkraft");
        expect(t).not.toContain("Lehrkräfte");
    });

    it("nennt Mitglieder ohne Rolle, wenn es sie gibt", () => {
        const t = vorschauText({ ...basis, anzahl: 2, schueler: 1, lehrkraefte: 0,
                                 ohne_rolle: 1, summe_eur: 1 });
        expect(t).toContain("1 ohne Rolle");
    });
});

describe("ergebnisText", () => {
    it("sagt bei Fehlschlägen, dass ein zweiter Versuch gefahrlos ist", () => {
        const t = ergebnisText({ gebucht: 27, fehlgeschlagen: ["a", "b"], unbegrenzt: [] });
        expect(t).toContain("27 gebucht");
        expect(t).toContain("2 nicht erreichbar");
        expect(t).toContain("gefahrlos");
    });

    it("bleibt knapp, wenn alles geklappt hat", () => {
        expect(ergebnisText({ gebucht: 3, fehlgeschlagen: [], unbegrenzt: [] })).toBe("3 gebucht.");
    });
});

describe("anfrage", () => {
    const gruppe = { modus: "gruppe", gruppeId: "7", mitglieder: "schueler",
                     betragEur: "0,50", grund: " Projektwoche " };

    it("baut die Gruppenanfrage und versteht das Komma", () => {
        expect(anfrage(gruppe)).toEqual({
            betrag_eur: 0.5, grund: "Projektwoche", gruppe_id: 7, mitglieder: "schueler",
        });
    });

    it("baut die Einzelanfrage aus der Kennung", () => {
        expect(anfrage({ modus: "person", kennungEingabe: " a3f9 c2b8 1e04 ",
                         betragEur: "1", grund: "Fortbildung" }))
            .toEqual({ betrag_eur: 1, grund: "Fortbildung", pseudonym: "a3f9 c2b8 1e04" });
    });

    it("ergibt nichts, solange etwas fehlt oder unsinnig ist", () => {
        expect(anfrage({ ...gruppe, betragEur: "" })).toBeNull();
        expect(anfrage({ ...gruppe, betragEur: "0" })).toBeNull();
        expect(anfrage({ ...gruppe, betragEur: "-1" })).toBeNull();
        expect(anfrage({ ...gruppe, grund: "  " })).toBeNull();
        expect(anfrage({ ...gruppe, gruppeId: "" })).toBeNull();
        expect(anfrage({ modus: "person", kennungEingabe: "", betragEur: "1", grund: "x" })).toBeNull();
    });
});

describe("schluessel", () => {
    it("ändert sich mit dem Betrag — eine geänderte Eingabe verlangt eine neue Prüfung", () => {
        const a = anfrage({ modus: "gruppe", gruppeId: "7", mitglieder: "schueler",
                            betragEur: "0,50", grund: "x" });
        const b = anfrage({ modus: "gruppe", gruppeId: "7", mitglieder: "schueler",
                            betragEur: "500", grund: "x" });
        expect(schluessel(a)).not.toBe(schluessel(b));
    });

    it("ändert sich mit dem Mitgliederfilter", () => {
        const basis = { modus: "gruppe", gruppeId: "7", betragEur: "1", grund: "x" };
        expect(schluessel(anfrage({ ...basis, mitglieder: "schueler" })))
            .not.toBe(schluessel(anfrage({ ...basis, mitglieder: "alle" })));
    });
});

describe("mitgliederVorgabe", () => {
    it("trifft bei Klassen und Unterrichtsgruppen die Schüler:innen", () => {
        expect(mitgliederVorgabe("teaching_group")).toBe("schueler");
        expect(mitgliederVorgabe("school_class")).toBe("schueler");
    });

    it("trifft bei Fachschaften die Lehrkräfte", () => {
        expect(mitgliederVorgabe("subject_department")).toBe("lehrkraefte");
    });
});

describe("eigeneKennung", () => {
    const p = "a3f9c2b81e04" + "0".repeat(52);

    it("zeigt Lehrkräften ihre Kennung", () => {
        expect(eigeneKennung({ pseudonym: p, roles: ["teacher"] })).toBe("a3f9 c2b8 1e04");
    });

    it("schließt Admins ein — Rollen sind additiv", () => {
        expect(eigeneKennung({ pseudonym: p, roles: ["teacher", "admin"] })).not.toBeNull();
    });

    it("zeigt Schüler:innen keine — sie bekommen Zuschläge über die Gruppe", () => {
        expect(eigeneKennung({ pseudonym: p, roles: ["student"] })).toBeNull();
    });

    it("schweigt ohne Nutzer", () => {
        expect(eigeneKennung(null)).toBeNull();
    });
});
