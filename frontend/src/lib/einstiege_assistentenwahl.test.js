/**
 * Wächter: Jeder Einstieg wählt seinen Assistenten über `passendeAssistenten` (0.15, Plan F7).
 *
 * Bis 0.14 nahm jeder Planungs-Einstieg „den ersten Assistenten mit `planning`" — mit einem
 * zweiten solchen Assistenten entschied die Sortierreihenfolge, wer antwortet. Die Regel steht
 * jetzt an **einer** Stelle (`$lib/assistentenwahl.js`, dort mit ihren Tests); hier wird nur
 * festgehalten, dass die Einstiege sie benutzen und keiner eine eigene Abkürzung nimmt.
 *
 * Quelltext statt Verhalten — aus demselben Grund wie in `picker_tastatur.test.js`: Das
 * Projekt mountet keine Svelte-Komponenten.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..");
const lies = (pfad) => readFileSync(join(SRC, pfad), "utf8");

const EINSTIEGE = [
    "routes/(app)/chat/+page.svelte",
    "routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte",
    "lib/components/TagesKachel.svelte",
];

function svelteDateien(verzeichnis) {
    return readdirSync(verzeichnis).flatMap((name) => {
        const pfad = join(verzeichnis, name);
        if (statSync(pfad).isDirectory()) return svelteDateien(pfad);
        return name.endsWith(".svelte") ? [pfad] : [];
    });
}

describe("Einstiege und ihr Assistent", () => {
    it.each(EINSTIEGE)("%s wählt über passendeAssistenten", (pfad) => {
        expect(lies(pfad)).toMatch(/passendeAssistenten\(/);
    });

    it("keine Komponente sucht selbst nach der Fähigkeit", () => {
        // Die Checkboxen des Editors dürfen die Fähigkeit nennen — sie wählen nichts aus.
        const abkuerzungen = svelteDateien(SRC)
            .filter((pfad) => !pfad.endsWith("AssistantEditor.svelte"))
            .filter((pfad) => /tool_groups\.includes\(\s*["'](lesson_)?planning["']/.test(
                readFileSync(pfad, "utf8")))
            .map((pfad) => relative(SRC, pfad));
        expect(abkuerzungen).toEqual([]);
    });

    it("gewählt wird aus GET /assistants, nicht aus einer Anzeigeliste", () => {
        // Die Entwurfsansicht und die Startseite laden die Liste selbst; die Chatseite
        // ebenso (`loadAssistants`). Eine gefilterte oder sortierte Anzeige (Päckchen C)
        // darf die Wahl nicht treffen.
        for (const pfad of [
            "routes/(app)/chat/+page.svelte",
            "routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte",
            "routes/(app)/welcome/+page.svelte",
        ]) {
            expect(lies(pfad), pfad).toMatch(/getAssistants\(\)/);
        }
    });

    it("kein Einstieg baut einen Chat-Link mit Gruppe von Hand", () => {
        // Seit 0.15 sagt ein Planungs-Einstieg ausdrücklich, welche Fähigkeit er sucht
        // (`faehigkeit=planning`). Ein handgebautes `/chat?group_id=…` sucht keine mehr —
        // es öffnete einen gewöhnlichen Chat statt der Jahresplanung.
        const handgebaut = svelteDateien(SRC)
            .filter((pfad) => readFileSync(pfad, "utf8").includes("/chat?group_id"))
            .map((pfad) => relative(SRC, pfad));
        expect(handgebaut).toEqual([]);
    });

    it.each([
        "routes/(app)/subjects/[slug]/groups/[id]/planner/+page.svelte",
        "routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte",
        "lib/components/planner/ReflowAssistbar.svelte",
    ])("%s nennt die Jahresplanung ausdrücklich", (pfad) => {
        expect(lies(pfad)).toMatch(/neuerChatPfad\(\{ groupId, faehigkeit: 'planning'/);
    });

    it("„Neuer Chat“ auf der Gruppenseite: mit Gruppe und Fach, ohne Fähigkeit", () => {
        // Todo „Schüler:in fragt nach der letzten Stunde", Punkt 1: Ohne Gruppenbezug fehlt
        // der Block „Aktueller Unterricht" — Schüler:innen landen genau hier.
        const quelle = lies("lib/components/GruppenUebersicht.svelte");
        expect(quelle).toMatch(/goto\(neuerChatPfad\(\{ subjectId: subject\?\.id, groupId: group\?\.id \}\)\)/);
        expect(quelle).not.toMatch(/goto\(['"]\/chat['"]\)/);
    });

    it("der geteilte Knopf zeigt den Pfeil erst bei zwei Kandidaten — oder zum Anlegen", () => {
        const quelle = lies("lib/components/AssistentenKnopf.svelte");
        expect(quelle).toMatch(
            /const mitPfeil = \$derived\(kandidaten\.length > 1 \|\| anlegen !== null\)/,
        );
        expect(quelle).toMatch(/\{#if mitPfeil\}/);
    });

    it("„Eigenen Stundenassistenten anlegen“ nur in der vollen Fassung (Plan Schritt 7)", () => {
        // Die kompakte der Startseite öffnet mit einem Kandidaten direkt (Jan, 09.10.2026);
        // ein Menüeintrag zum Anlegen machte daraus wieder einen Tipp mehr.
        expect(lies("lib/components/AssistentenKnopf.svelte")).toMatch(
            /const anlegen = \$derived\(!kompakt && onanlegen \? onanlegen : null\)/,
        );
    });

    it.each([
        "routes/(app)/subjects/[slug]/groups/[id]/planner/lessons/[nodeId]/+page.svelte",
        "routes/(app)/assistants/my/+page.svelte",
    ])("%s legt den eigenen Stundenassistenten an und öffnet den Editor", (pfad) => {
        const quelle = lies(pfad);
        expect(quelle).toMatch(/await legeEigenenStundenassistentenAn\(/);
        expect(quelle).toMatch(/goto\(`\/assistants\/my\/\$\{/);
    });

    it("die Entwurfsansicht bietet das Anlegen im geteilten Knopf an — mit dem Fach der Stunde", () => {
        const quelle = lies(EINSTIEGE[1]);
        expect(quelle).toMatch(/onanlegen=\{stundenAssistenten\.length \? eigenenAnlegen : null\}/);
        expect(quelle).toMatch(/legeEigenenStundenassistentenAn\(\{ subjectId: lesson\?\.subject_id/);
    });

    it("kompakt ab zwei Kandidaten öffnet immer das Menü, nie den ersten", () => {
        // Jan, 09.10.2026: Auf dem Telefon traf man statt des kleinen Pfeils den Hauptteil
        // und landete ungefragt beim ersten Assistenten.
        const quelle = lies("lib/components/AssistentenKnopf.svelte");
        expect(quelle).toMatch(/const nurMenue = \$derived\(kompakt && kandidaten\.length > 1\)/);
        const zweig = quelle.slice(quelle.indexOf("{#if nurMenue}"), quelle.indexOf("{:else}"));
        expect(zweig).toMatch(/onclick=\{\(\) => \(offen = !offen\)\}/);
        expect(zweig).not.toMatch(/waehle\(/);
    });
});
