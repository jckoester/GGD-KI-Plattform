import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { loeschsperre } from "./assistant_lebenszyklus.js";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const lies = (pfad) => readFileSync(join(SRC, pfad), "utf8");

// Dieselbe Matrix wie `tests/unit/test_assistant_lebenszyklus.py` — beide Richtungen.
describe("loeschsperre", () => {
  it.each(["private", "teaching_group", "subject_department", "activity_group"])(
    "%s: jederzeit löschbar",
    (scope) => {
      for (const status of ["active", "draft", "disabled", "pending_review"]) {
        expect(loeschsperre({ scope, status })).toBeNull();
      }
    },
  );

  it.each(["teachers", "grade", "all_students", "all"])("%s: nur vor der Freigabe", (scope) => {
    expect(loeschsperre({ scope, status: "draft" })).toBeNull();
    expect(loeschsperre({ scope, status: "pending_review" })).toBeNull();
    expect(loeschsperre({ scope, status: "active" })).toMatch(/beantragt/);
    expect(loeschsperre({ scope, status: "disabled" })).toMatch(/beantragt/);
  });
});

// Quelltext statt Verhalten — das Projekt mountet keine Svelte-Komponenten.
describe("Wächter: Editor und „Meine Assistenten“ (0.15)", () => {
  const EDITOR = "lib/components/AssistantEditor.svelte";
  const LISTE = "routes/(app)/assistants/my/+page.svelte";

  it("beide fragen loeschsperre, keiner eine eigene Statusliste", () => {
    expect(lies(EDITOR)).toMatch(/loeschsperre\(savedForm\) === null/);
    expect(lies(LISTE)).toMatch(/loeschsperre\(item\) === null/);
    // Bis 0.15 bot die Liste den Papierkorb nur im Entwurf und in der Prüfung an.
    expect(lies(LISTE)).not.toMatch(/Nur Assistenten im Status/);
  });

  it("der Editor einer Lehrkraft zeigt ihre Fächer, die Verwaltung alle", () => {
    const quelle = lies(EDITOR);
    expect(quelle).toMatch(/isAdmin \? subjects : eigeneFaecher\(subjects, groups, savedForm\.subject_id\)/);
    expect(quelle).toMatch(/\{#each faecherAuswahl as subject/);
    expect(quelle).not.toMatch(/\{#each subjects as subject/);
  });
});
