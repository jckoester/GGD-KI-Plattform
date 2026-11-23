import { describe, expect, it } from "vitest";
import { aufteilen } from "./zugangstoken_listen.js";

const JETZT = new Date("2026-11-23T12:00:00Z");
const BALD = "2027-02-01T00:00:00Z";
const VORBEI = "2026-11-01T00:00:00Z";

describe("Token-Liste im Profil", () => {
  it("trennt verbundene Programme von eigenen Zugangstoken", () => {
    const { programme, eigene } = aufteilen([
      { id: 1, expires_at: BALD },
      { id: 2, expires_at: BALD, oauth_client_id: "c1" },
      { id: 3, expires_at: BALD, oauth_client_id: "c1", revoked_at: VORBEI },  // ersetzt
      { id: 4, expires_at: VORBEI, oauth_client_id: "c2" },                   // abgelaufen
      { id: 5, expires_at: VORBEI, revoked_at: VORBEI },
    ], JETZT);
    expect(programme.map((e) => e.id)).toEqual([2]);
    expect(eigene.map((e) => e.id)).toEqual([1, 5]);  // eigene auch beendet — wie bisher
  });
});
