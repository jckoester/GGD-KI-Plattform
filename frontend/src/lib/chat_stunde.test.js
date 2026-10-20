import { describe, expect, it } from "vitest";
import { stundenDatum, stundenPfad, stundenText } from "./chat_stunde.js";

const STUNDE = {
  stunde_node_id: "00318c0f-8315-4a87-8e37-639482b91306",
  titel: "Rechnen mit Potenzen",
  datum: "2026-10-14",
  group_id: 36,
  fach_slug: "mathematik",
};

describe("chat_stunde", () => {
  it("baut den Pfad zur Entwurfsansicht", () => {
    expect(stundenPfad(STUNDE)).toBe(
      "/subjects/mathematik/groups/36/planner/lessons/00318c0f-8315-4a87-8e37-639482b91306",
    );
  });

  it("ohne Teile kein Pfad", () => {
    expect(stundenPfad(null)).toBeNull();
    expect(stundenPfad({ ...STUNDE, fach_slug: null })).toBeNull();
    expect(stundenPfad({ ...STUNDE, group_id: null })).toBeNull();
  });

  it("beschriftet mit Titel und Wochentag", () => {
    expect(stundenDatum("2026-10-14")).toBe("Mi 14.10.");
    expect(stundenText(STUNDE)).toBe("Rechnen mit Potenzen · Mi 14.10.");
    expect(stundenText({ ...STUNDE, datum: null })).toBe("Rechnen mit Potenzen");
    expect(stundenDatum("kaputt")).toBe("");
  });
});
