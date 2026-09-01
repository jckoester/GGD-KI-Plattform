import { describe, expect, it } from "vitest";

import { umschlagAlsListe } from "./api.js";

/**
 * Der Ergebnisumschlag (ADR-017) trennt, was die alte Trefferliste vermischte:
 * Bausteine, die den gesuchten Namen **tragen**, und Bausteine, die ihm nur ähneln.
 * Bis das Vorschlagsfenster die Abschnitte getrennt zeigt (AP8), macht diese Funktion
 * sie flach — die Reihenfolge ist dabei die Aussage.
 */
describe("umschlagAlsListe", () => {
  const umschlag = {
    identifikation: {
      treffer: [{ node_id: "a", title: "nennen" }],
      gesamt: 24,
      vollstaendig: false,
    },
    thematisch: {
      treffer: [{ node_id: "b", title: "beschreiben" }],
      gesamt: null,
      vollstaendig: false,
    },
    hinweise: [],
  };

  it("stellt die Namensträger voran", () => {
    expect(umschlagAlsListe(umschlag).map((t) => t.node_id)).toEqual(["a", "b"]);
  });

  it("führt einen Knoten nur einmal", () => {
    const doppelt = {
      identifikation: { treffer: [{ node_id: "a" }] },
      thematisch: { treffer: [{ node_id: "a" }, { node_id: "b" }] },
    };
    expect(umschlagAlsListe(doppelt).map((t) => t.node_id)).toEqual(["a", "b"]);
  });

  it("kommt mit leeren Abschnitten zurecht", () => {
    expect(umschlagAlsListe({ identifikation: {}, thematisch: {} })).toEqual([]);
  });

  it("wirft nicht, wenn gar kein Umschlag ankommt", () => {
    // Fehlerpfade im Chat setzen die Vorschlagsliste zurück — sie dürfen nicht
    // ihrerseits eine Ausnahme auslösen.
    expect(umschlagAlsListe(null)).toEqual([]);
    expect(umschlagAlsListe(undefined)).toEqual([]);
  });
});
