import { describe, expect, it } from "vitest";

import { ANFRAGE_MAX, mentionAnfrage, ohneMentionFragment } from "./mention.js";

describe("mentionAnfrage", () => {
  it("liest die Anfrage hinter dem @", () => {
    expect(mentionAnfrage("@nennen")).toBe("nennen");
  });

  it("beginnt leer, sobald das @ steht", () => {
    // Kein `null`: Das Dropdown soll sich öffnen und die ersten Treffer zeigen.
    expect(mentionAnfrage("@")).toBe("");
  });

  it("lässt Leerzeichen zu", () => {
    // Der Kern von AP9: Mit `@` sucht man nach bekannten, mehrwortigen Titeln.
    expect(mentionAnfrage("@Satz des Pythagoras")).toBe("Satz des Pythagoras");
    expect(mentionAnfrage("@Anleitung für den Operator nennen")).toBe(
      "Anleitung für den Operator nennen",
    );
  });

  it("findet das @ auch mitten im Satz", () => {
    expect(mentionAnfrage("Erkläre mir @Satz des")).toBe("Satz des");
  });

  it("nimmt das letzte @, nicht das erste", () => {
    expect(mentionAnfrage("@erstes und @zweites")).toBe("zweites");
  });

  it("greift nicht in einer E-Mail-Adresse", () => {
    // Ohne die Wortgrenze würde „jan@example.de und dann noch …“ den halben Satz
    // als Anfrage schicken.
    expect(mentionAnfrage("jan@example.de")).toBeNull();
    expect(mentionAnfrage("Schreib an jan@example.de bitte")).toBeNull();
  });

  it("gibt ohne @ nichts zurück", () => {
    expect(mentionAnfrage("nennen")).toBeNull();
    expect(mentionAnfrage("")).toBeNull();
    expect(mentionAnfrage(undefined)).toBeNull();
  });

  it("endet an einem Zeilenumbruch", () => {
    // Eine neue Zeile ist ein neuer Gedanke — die Anfrage darf nicht darüber hinweg.
    expect(mentionAnfrage("@nennen\nund weiter")).toBeNull();
  });

  it("gibt sehr lange Anfragen auf", () => {
    // Fließtext hinter einem @. Der Deckel greift, bevor „keine Treffer“ greifen kann.
    expect(mentionAnfrage("@" + "x".repeat(ANFRAGE_MAX))).toHaveLength(ANFRAGE_MAX);
    expect(mentionAnfrage("@" + "x".repeat(ANFRAGE_MAX + 1))).toBeNull();
  });
});

describe("ohneMentionFragment", () => {
  it("entfernt das Fragment", () => {
    expect(ohneMentionFragment("@nennen")).toBe("");
  });

  it("entfernt auch mehrwortige Fragmente", () => {
    // Sonst bliebe beim Übernehmen eines Treffers ein Rest im Eingabefeld stehen —
    // deshalb muss dieselbe Stelle getroffen werden wie beim Auslesen.
    expect(ohneMentionFragment("Erkläre mir @Satz des Pyth")).toBe("Erkläre mir ");
  });

  it("lässt eine E-Mail-Adresse stehen", () => {
    expect(ohneMentionFragment("Schreib an jan@example.de")).toBe(
      "Schreib an jan@example.de",
    );
  });

  it("lässt Text ohne @ unberührt", () => {
    expect(ohneMentionFragment("nennen")).toBe("nennen");
  });
});
