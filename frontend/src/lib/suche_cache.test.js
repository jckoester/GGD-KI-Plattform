import { beforeEach, describe, expect, it } from "vitest";

import { holen, leeren, merken, suchSchluessel } from "./suche_cache.js";

describe("suche_cache", () => {
  beforeEach(() => leeren());

  const umschlag = (n) => ({ identifikation: { treffer: [{ node_id: n }] } });

  it("gibt ein gemerktes Ergebnis zurück", () => {
    const s = suchSchluessel({ q: "nennen" });
    merken(s, umschlag("a"));
    expect(holen(s)).toEqual(umschlag("a"));
  });

  it("kennt eine unbekannte Suche nicht", () => {
    expect(holen(suchSchluessel({ q: "nie gesucht" }))).toBeNull();
  });

  it("unterscheidet nach Facetten", () => {
    // Sonst zeigte die Suchseite nach dem Setzen eines Filters das ungefilterte
    // Ergebnis — mit einer Zählung, die zu den Filtern nicht passt.
    merken(suchSchluessel({ q: "nennen" }), umschlag("ohne"));
    expect(holen(suchSchluessel({ q: "nennen", typ: "operator" }))).toBeNull();
  });

  it("behandelt Zahl und Zeichenkette gleich", () => {
    // Die Fachauswahl liefert eine Zeichenkette, die URL ebenso — ein Wechsel des
    // Typs darf nicht als andere Suche gelten.
    merken(suchSchluessel({ q: "x", fach: 7 }), umschlag("a"));
    expect(holen(suchSchluessel({ q: "x", fach: "7" }))).toEqual(umschlag("a"));
  });

  it("ignoriert Randleerzeichen der Anfrage", () => {
    merken(suchSchluessel({ q: "nennen" }), umschlag("a"));
    expect(holen(suchSchluessel({ q: "  nennen " }))).toEqual(umschlag("a"));
  });

  it("verwirft die am längsten ungenutzte Suche", () => {
    for (let i = 0; i < 9; i++) merken(suchSchluessel({ q: `s${i}` }), umschlag(i));
    expect(holen(suchSchluessel({ q: "s0" }))).toBeNull();
    expect(holen(suchSchluessel({ q: "s8" }))).not.toBeNull();
  });

  it("frischt beim Lesen die Reihenfolge auf", () => {
    // Die Suche, zu der man immer wieder zurückkehrt, soll nicht herausfallen, nur
    // weil sie als erste gemerkt wurde.
    for (let i = 0; i < 8; i++) merken(suchSchluessel({ q: `s${i}` }), umschlag(i));
    holen(suchSchluessel({ q: "s0" }));
    merken(suchSchluessel({ q: "neu" }), umschlag("neu"));
    expect(holen(suchSchluessel({ q: "s0" }))).not.toBeNull();
    expect(holen(suchSchluessel({ q: "s1" }))).toBeNull();
  });

  it("merkt nichts ohne Ergebnis", () => {
    const s = suchSchluessel({ q: "x" });
    merken(s, null);
    expect(holen(s)).toBeNull();
  });
});
