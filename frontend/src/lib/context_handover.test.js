import { beforeEach, describe, expect, it } from "vitest";

import { fuerNeuenChat, uebernehmen } from "./context_handover.js";

/**
 * Die Übergabe von der Suchseite in einen neuen Chat. Sie ist bewusst **einmalig**:
 * Bliebe sie liegen, tauchten dieselben Bausteine beim nächsten neuen Chat wieder auf,
 * ohne dass jemand sie angefordert hat — und niemand käme auf die Idee, das mit einer
 * Suche von vorgestern in Verbindung zu bringen.
 */
describe("context_handover", () => {
  beforeEach(() => sessionStorage.clear());

  const knoten = [
    { node_id: "a", title: "Bruchrechnung", category: "knowledge", content_type: "leitidee" },
    { node_id: "b", title: "Anteile", category: "knowledge", content_type: "ik_kompetenz" },
  ];

  it("gibt die Auswahl weiter", () => {
    fuerNeuenChat(knoten);
    expect(uebernehmen().map((n) => n.node_id)).toEqual(["a", "b"]);
  });

  it("verbraucht die Übergabe", () => {
    fuerNeuenChat(knoten);
    uebernehmen();
    expect(uebernehmen()).toEqual([]);
  });

  it("überträgt nur die Anzeigefelder", () => {
    fuerNeuenChat([{ ...knoten[0], content: "langer Text", geheim: true }]);
    const [uebernommen] = uebernehmen();
    expect(uebernommen).toEqual(knoten[0]);
  });

  it("legt für eine leere Auswahl nichts ab", () => {
    fuerNeuenChat([]);
    expect(sessionStorage.getItem("kontext-uebergabe")).toBeNull();
  });

  it("kommt mit beschädigtem Inhalt zurecht", () => {
    // Etwa nach einem Formatwechsel zwischen zwei Versionen — der Chat darf davon
    // nicht abstürzen, er startet dann eben ohne Bausteine.
    sessionStorage.setItem("kontext-uebergabe", "{kein json");
    expect(uebernehmen()).toEqual([]);
  });

  it("ohne Übergabe eine leere Liste", () => {
    expect(uebernehmen()).toEqual([]);
  });
});
