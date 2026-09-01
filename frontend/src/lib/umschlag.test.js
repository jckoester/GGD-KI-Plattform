import { describe, expect, it } from "vitest";

import {
  ABSCHNITT_TITEL,
  PRO_ABSCHNITT_VORAUSGEWAEHLT,
  alleTreffer,
  gueltigeAuswahl,
  vorauswahl,
  vorschlagsAbschnitte,
} from "./umschlag.js";

const treffer = (node_id, treffer_art = "exakt") => ({
  node_id,
  title: node_id,
  category: "curriculum",
  content_type: "ik",
  treffer_art,
});

const umschlag = ({ ident = [], gesamt = null, vollstaendig = true, thema = [] } = {}) => ({
  identifikation: {
    treffer: ident,
    gesamt: gesamt ?? ident.filter((t) => t.treffer_art !== "teilweise").length,
    vollstaendig,
  },
  thematisch: { treffer: thema },
  hinweise: [],
});

const schluessel = (abschnitte) => abschnitte.map((a) => a.schluessel);

describe("vorschlagsAbschnitte", () => {
  it("trennt Namensträger, ähnlich benannte und thematische Treffer", () => {
    const abschnitte = vorschlagsAbschnitte(
      umschlag({
        ident: [treffer("a"), treffer("b", "teilweise")],
        thema: [treffer("c", null)],
      }),
    );
    expect(schluessel(abschnitte)).toEqual(["exakt", "aehnlich", "thematisch"]);
    expect(abschnitte[0].titel).toBe(ABSCHNITT_TITEL.exakt);
    expect(abschnitte.map((a) => a.treffer.map((t) => t.node_id))).toEqual([
      ["a"],
      ["b"],
      ["c"],
    ]);
  });

  it("lässt leere Abschnitte weg", () => {
    // Eine Überschrift ohne Treffer wäre im knappen Fenster verschenkte Höhe.
    const abschnitte = vorschlagsAbschnitte(umschlag({ thema: [treffer("c", null)] }));
    expect(schluessel(abschnitte)).toEqual(["thematisch"]);
  });

  it("zeigt jeden Treffer nur einmal, und zwar als Namensträger", () => {
    // Der gesuchte Baustein kann Namensträger und thematisch nah zugleich sein.
    const abschnitte = vorschlagsAbschnitte(
      umschlag({ ident: [treffer("a")], thema: [treffer("a", null), treffer("b", null)] }),
    );
    expect(alleTreffer(abschnitte).map((t) => t.node_id)).toEqual(["a", "b"]);
    expect(abschnitte[1].treffer.map((t) => t.node_id)).toEqual(["b"]);
  });

  it("verträgt einen leeren oder fehlenden Umschlag", () => {
    expect(vorschlagsAbschnitte({ identifikation: {}, thematisch: {} })).toEqual([]);
    expect(vorschlagsAbschnitte(null)).toEqual([]);
    expect(vorschlagsAbschnitte(undefined)).toEqual([]);
  });

  it("nennt bei vollständiger Identifikation nur die Zahl", () => {
    const [exakt] = vorschlagsAbschnitte(umschlag({ ident: [treffer("a"), treffer("b")] }));
    expect(exakt.fussnote).toBe("2 gefunden");
    expect(exakt.gekuerzt).toBe(false);
  });

  it("weist gekürzte Identifikation als gekürzt aus", () => {
    // Erst das macht den Verweis auf die Suchseite ehrlich: Es gibt mehr, als hier steht.
    const [exakt] = vorschlagsAbschnitte(
      umschlag({ ident: [treffer("a")], gesamt: 24, vollstaendig: false }),
    );
    expect(exakt.fussnote).toBe("1 von 24 angezeigt");
    expect(exakt.gekuerzt).toBe(true);
  });

  it("hält die Teiltreffer ohne Zahl", () => {
    // Ihre Menge hängt an einer Ähnlichkeitsschwelle — eine Zahl daraus zu machen,
    // hieße die Schwelle als Wahrheit auszugeben.
    const [aehnlich] = vorschlagsAbschnitte(
      umschlag({ ident: [treffer("a", "teilweise")] }),
    );
    expect(aehnlich.fussnote).not.toMatch(/\d/);
  });
});

describe("vorauswahl", () => {
  it("wählt die Namensträger vor", () => {
    const abschnitte = vorschlagsAbschnitte(
      umschlag({ ident: [treffer("a"), treffer("b")] }),
    );
    expect([...vorauswahl(abschnitte)]).toEqual(["a", "b"]);
  });

  it("deckelt auch die Namensträger", () => {
    // Gemessen: „nennen" tragen 24 Bausteine — der Operator steht in jedem Fach und
    // jeder Edition. Viele Gleichnamige heißen nicht „alle gemeint", sondern
    // „der Name war mehrdeutig".
    const ident = Array.from({ length: 24 }, (_, i) => treffer(`n${i}`));
    const gewaehlt = vorauswahl(vorschlagsAbschnitte(umschlag({ ident })));
    expect(gewaehlt.size).toBe(PRO_ABSCHNITT_VORAUSGEWAEHLT);
    expect(gewaehlt.has("n0")).toBe(true);
  });

  it("wählt ähnlich benannte nicht vor", () => {
    // Sie können der gesuchte Baustein sein oder ein anderer mit ähnlichem Titel.
    const abschnitte = vorschlagsAbschnitte(
      umschlag({ ident: [treffer("a", "teilweise")] }),
    );
    expect(vorauswahl(abschnitte).size).toBe(0);
  });

  it("begrenzt die thematische Vorauswahl", () => {
    // Sonst hieße „Hinzufügen" bei Anzeigelimit 30 bis zu 60 angeheftete Bausteine.
    const thema = Array.from({ length: 12 }, (_, i) => treffer(`t${i}`, null));
    const abschnitte = vorschlagsAbschnitte(umschlag({ thema }));
    const gewaehlt = vorauswahl(abschnitte);
    expect(gewaehlt.size).toBe(PRO_ABSCHNITT_VORAUSGEWAEHLT);
    expect(gewaehlt.has("t0")).toBe(true);
    expect(gewaehlt.has(`t${PRO_ABSCHNITT_VORAUSGEWAEHLT}`)).toBe(false);
  });

  it("wählt bei leerem Ergebnis nichts vor", () => {
    expect(vorauswahl(vorschlagsAbschnitte(null)).size).toBe(0);
  });
});

describe("gueltigeAuswahl", () => {
  const erster = umschlag({ ident: [treffer("a"), treffer("b")] });
  const zweiter = umschlag({ ident: [treffer("x")] });

  it("nimmt ohne Handauswahl die Vorauswahl", () => {
    const abschnitte = vorschlagsAbschnitte(erster);
    expect([...gueltigeAuswahl(null, erster, abschnitte)]).toEqual(["a", "b"]);
  });

  it("behält die Handauswahl zum selben Umschlag", () => {
    const abschnitte = vorschlagsAbschnitte(erster);
    const hand = { umschlag: erster, ids: new Set(["b"]) };
    expect([...gueltigeAuswahl(hand, erster, abschnitte)]).toEqual(["b"]);
  });

  it("verwirft die Handauswahl, wenn ein neuer Umschlag kommt", () => {
    // Der latente Bug: Eine zweite Suche bei offenem Fenster behielt die alten IDs.
    // Der Knopf zeigte „Hinzufügen (1)", bestätigt wurde nichts — die ID kam in der
    // neuen Trefferliste nicht vor.
    const abschnitte = vorschlagsAbschnitte(zweiter);
    const hand = { umschlag: erster, ids: new Set(["b"]) };
    expect([...gueltigeAuswahl(hand, zweiter, abschnitte)]).toEqual(["x"]);
  });

  it("lässt eine leere Handauswahl leer", () => {
    // Wer alles abwählt, will nichts — nicht die Vorauswahl zurück.
    const abschnitte = vorschlagsAbschnitte(erster);
    const hand = { umschlag: erster, ids: new Set() };
    expect(gueltigeAuswahl(hand, erster, abschnitte).size).toBe(0);
  });
});
