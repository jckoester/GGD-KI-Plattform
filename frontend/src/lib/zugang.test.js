import { describe, it, expect, vi, beforeEach } from "vitest";
import { get } from "svelte/store";

vi.mock("$lib/api.js", () => ({ getMe: vi.fn() }));

import { user } from "$lib/stores/user.js";
import { nutzer, hatRolle } from "./zugang.js";

describe("nutzer (Wächter in +page.js, 0.27)", () => {
  beforeEach(() => user.set(null));

  it("Store leer: holt /auth/me, statt null zu melden — der Fall Neuladen", async () => {
    const holen = vi.fn().mockResolvedValue({ pseudonym: "p", roles: ["teacher", "admin"] });
    const n = await nutzer({ holen });
    expect(n.roles).toContain("admin");
    expect(get(user).pseudonym).toBe("p");
    expect(holen).toHaveBeenCalledTimes(1);
  });

  it("Store gefüllt: keine Anfrage", async () => {
    user.set({ pseudonym: "q", roles: ["student"] });
    const holen = vi.fn();
    expect((await nutzer({ holen })).pseudonym).toBe("q");
    expect(holen).not.toHaveBeenCalled();
  });

  it("gleichzeitige Aufrufe teilen sich eine Anfrage", async () => {
    const holen = vi.fn().mockResolvedValue({ pseudonym: "p", roles: [] });
    await Promise.all([nutzer({ holen }), nutzer({ holen })]);
    expect(holen).toHaveBeenCalledTimes(1);
  });

  it("Anfrage scheitert: null", async () => {
    expect(await nutzer({ holen: () => Promise.reject(new Error("401")) })).toBeNull();
  });

  it("hatRolle", async () => {
    user.set({ pseudonym: "q", roles: ["teacher", "statistics"] });
    expect(await hatRolle("statistics", "admin")).toBe(true);
    expect(await hatRolle("admin")).toBe(false);
  });
});

describe("Wächter: kein get(user) in +page.js", () => {
  it("jede Rollenprüfung in einer load-Funktion wartet über nutzer()", () => {
    const dateien = import.meta.glob("../routes/**/+page.js", { query: "?raw", import: "default", eager: true });
    const treffer = Object.entries(dateien).filter(([, quelle]) => quelle.includes("get(user)")).map(([p]) => p);
    expect(Object.keys(dateien).length).toBeGreaterThan(10);
    expect(treffer).toEqual([]);
  });
});
