import { describe, expect, it } from "vitest";
import {
  EMPFOHLEN_MAX, MAX_EINTRAEGE, MAX_ZEICHEN, listenHinweis, listeZuZeilen, zeilenZuListe,
} from "./ausloeser_editor.js";

describe("zeilenZuListe / listeZuZeilen", () => {
  it("trimmt, lässt Leerzeilen und Dubletten weg, Reihenfolge bleibt", () => {
    expect(zeilenZuListe("  b \n\na\nb\n   \nc")).toEqual(["b", "a", "c"]);
  });
  it("Groß-/Kleinschreibung bleibt verschieden — wie der Server", () => {
    expect(zeilenZuListe("Mol\nmol")).toEqual(["Mol", "mol"]);
  });
  it("null (nicht geladen) und Rundreise", () => {
    expect(listeZuZeilen(null)).toBe("");
    expect(zeilenZuListe(listeZuZeilen(["x", "y"]))).toEqual(["x", "y"]);
  });
});

describe("listenHinweis", () => {
  const zeilen = (n) => Array.from({ length: n }, (_, i) => `t${i}`).join("\n");

  it("zählt", () => {
    expect(listenHinweis(zeilen(1), "beispiel", "never").zaehler).toMatch(/^1 Beispiel ·/);
    expect(listenHinweis(zeilen(3), "gegenbeispiel", "never").zaehler).toMatch(/^3 Gegenbeispiele/);
  });
  it("ohne Beispiele kein Vorschlag — nur wenn vorgeschlagen werden soll", () => {
    expect(listenHinweis("", "beispiel", "specific").warnung).toMatch(/nicht vorgeschlagen/);
    expect(listenHinweis("", "beispiel", "never").warnung).toBeUndefined();
    expect(listenHinweis("", "gegenbeispiel", "specific").warnung).toBeUndefined();
  });
  it("unter fünf: unsicher; fünf: still", () => {
    expect(listenHinweis(zeilen(4), "beispiel", "fallback").warnung).toMatch(/unsicher/);
    expect(listenHinweis(zeilen(5), "beispiel", "fallback")).toEqual({
      zaehler: expect.any(String),
    });
  });
  it("über der Empfehlung warnt, über der Grenze ist es ein Fehler", () => {
    expect(listenHinweis(zeilen(EMPFOHLEN_MAX + 1), "beispiel", "never").warnung).toMatch(/breiter/);
    expect(listenHinweis(zeilen(MAX_EINTRAEGE + 1), "beispiel", "never").fehler).toMatch(/Höchstens/);
    expect(listenHinweis("x".repeat(MAX_ZEICHEN + 1), "beispiel", "never").fehler).toMatch(/Zeichen/);
  });
});

// Quelltext statt Verhalten — das Projekt mountet keine Svelte-Komponenten.
import { readFileSync } from "node:fs";
import { join } from "node:path";

describe("Wächter: Editor verdrahtet die Listen (C1 Schritt 4)", () => {
  const quelle = readFileSync(join(import.meta.dirname, "components/AssistantEditor.svelte"), "utf8");

  it("lädt als Zeilen und sendet als Liste", () => {
    expect(quelle).toMatch(/trigger_examples: listeZuZeilen\(a\.trigger_examples\)/);
    expect(quelle).toMatch(/trigger_counterexamples: listeZuZeilen\(a\.trigger_counterexamples\)/);
    expect(quelle).toMatch(/trigger_examples: zeilenZuListe\(form\.trigger_examples\)/);
    expect(quelle).toMatch(/trigger_counterexamples: zeilenZuListe\(form\.trigger_counterexamples\)/);
    expect(quelle).toMatch(/suggest: form\.suggest,/);
  });

  it("hat Felder für beide Listen und suggest", () => {
    for (const id of ["ae-suggest", "ae-trigger-examples", "ae-trigger-counterexamples"])
      expect(quelle).toContain(`id="${id}"`);
    expect(quelle).toMatch(/bind:value=\{form\.suggest\}/);
  });

  it("eine Kopie wird nicht vorgeschlagen", () => {
    expect(quelle).toMatch(/Kopie von \$\{template\.name\}`,[\s\S]{0,400}suggest: "never"/);
  });
});
