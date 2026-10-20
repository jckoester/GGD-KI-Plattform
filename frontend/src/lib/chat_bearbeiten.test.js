import { describe, expect, it } from "vitest";
import { hatteAnhaenge, istAbbruch, istBearbeitbar, letzteEigeneIndex, wirkungsHinweis } from "./chat_bearbeiten.js";

const U = (c) => ({ role: "user", content: c });
const A = (c, extra = {}) => ({ role: "assistant", content: c, ...extra });

describe("letzteEigeneIndex", () => {
  it("findet die letzte eigene Nachricht vor ihrer Antwort", () => {
    expect(letzteEigeneIndex([U("a"), A("1"), U("b"), A("2")])).toBe(2);
    expect(letzteEigeneIndex([U("a"), A("1"), U("b")])).toBe(2);
    expect(letzteEigeneIndex([U("a"), { role: "error", content: "x" }])).toBe(0);
    expect(letzteEigeneIndex([])).toBe(-1);
  });

  it("nur mit Konversation und nicht während des Streamens", () => {
    const m = [U("a"), A("1")];
    expect(istBearbeitbar(m, 0, { conversationId: "k" })).toBe(true);
    expect(istBearbeitbar(m, 0, { conversationId: null })).toBe(false);
    expect(istBearbeitbar(m, 0, { conversationId: "k", isStreaming: true })).toBe(false);
    expect(istBearbeitbar([U("a"), A("1"), U("b"), A("2")], 0, { conversationId: "k" })).toBe(false);
  });
});

describe("wirkungsHinweis", () => {
  it("nennt, was bleibt", () => {
    const text = wirkungsHinweis(A("x", { werkzeuge_mit_wirkung: ["update_lesson_phases"], images: [{}] }));
    expect(text).toContain("den Stundenentwurf geändert und ein Bild erzeugt");
    expect(text).toContain("bleibt bestehen");
  });

  it("schweigt ohne Wirkung", () => {
    expect(wirkungsHinweis(A("x"))).toBeNull();
    expect(wirkungsHinweis(null)).toBeNull();
  });
});

describe("Kleinigkeiten", () => {
  it("Anhänge aus der Sitzung und aus dem Verlauf", () => {
    expect(hatteAnhaenge({ uploadedAttachments: [{}] })).toBe(true);
    expect(hatteAnhaenge({ attachments: [{ name: "a.pdf" }] })).toBe(true);
    expect(hatteAnhaenge(U("a"))).toBe(false);
  });

  it("erkennt den gewollten Abbruch", () => {
    const c = new AbortController();
    c.abort();
    expect(istAbbruch(new Error("x"), c.signal)).toBe(true);
    expect(istAbbruch({ name: "AbortError" }, null)).toBe(true);
    expect(istAbbruch(new Error("Netz"), new AbortController().signal)).toBe(false);
  });
});
