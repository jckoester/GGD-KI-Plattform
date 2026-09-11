/**
 * Wächter über die Tastaturbedienung der Overlay-Dialoge in der Chat-Eingabe.
 *
 * Anlass (10.09.2026): Der `AssistantPicker` (`/` im Chat) fokussierte sein Suchfeld
 * beim Öffnen nicht. Weil `handleKeydown` an ebendiesem Feld hängt, waren damit
 * **Escape, Pfeiltasten und Enter zugleich tot** — der Tastaturfokus blieb im
 * Chat-Textfeld, und Getipptes landete dort. Übrig blieb, einen Eintrag anzuklicken.
 * Der `SubjectPicker` (`#`) machte es zwei Dateien weiter richtig; der Kommentar im
 * `AssistantPicker` kündigte den Aufruf sogar an, der Aufruf fehlte.
 *
 * Der Fehler ist von außen **unsichtbar**: Der Dialog erscheint, sieht fertig aus und
 * reagiert auf die Maus. Genau deshalb steht hier ein Wächter statt eines Kommentars.
 *
 * ⚠️ **Warum Quelltext statt Verhalten.** Das Projekt hat keine
 * Svelte-Komponententests — die 551 Frontend-Tests prüfen Logikmodule. Eine
 * Komponente zu mounten verlangte `@testing-library/svelte`, und jede neue
 * Abhängigkeit trägt hier eine Obergrenze und einen neu zu erzeugenden Lockfile
 * (Sicherheits-Audit #17). Für eine Regel dieser Form — „wer Tasten annimmt, muss
 * den Fokus holen" — ist die Quelle die ehrlichere Prüfung als ein nachgestelltes
 * DOM.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const KOMPONENTEN = join(dirname(fileURLToPath(import.meta.url)), "components");

/**
 * Die schließbaren Overlay-Dialoge mit eigenem Suchfeld.
 *
 * Zwei Merkmale zusammen, nicht eines: ein `<input>` mit `onkeydown` **und** ein
 * `onclose`-Prop. Das erste allein trifft auch gewöhnliche Formularfelder
 * (`AliasFeld`, `CollectionEditor`, `ConversationMenu`) — die sollen den Fokus
 * gerade **nicht** an sich reißen, sie stehen ja schon auf der Seite. Ein
 * `onclose`-Prop hat nur, was aufgeht und wieder zugeht.
 */
function tastaturkomponenten() {
    return readdirSync(KOMPONENTEN)
        .filter((n) => n.endsWith(".svelte"))
        .map((name) => ({ name, quelle: readFileSync(join(KOMPONENTEN, name), "utf8") }))
        .filter(
            ({ quelle }) =>
                /<input\b[^>]*onkeydown=\{/s.test(quelle) && /onclose\b/.test(quelle),
        );
}

describe("Overlay-Dialoge: Tastaturbedienung", () => {
    it("findet überhaupt Komponenten mit Tastatur-Suchfeld", () => {
        // Sonst prüfte der Test unten eine leere Menge und wäre immer grün — etwa
        // wenn sich die Schreibweise des Attributs ändert.
        expect(tastaturkomponenten().length).toBeGreaterThanOrEqual(2);
    });

    it("fokussiert das Suchfeld beim Öffnen", () => {
        const fehlend = tastaturkomponenten()
            .filter(({ quelle }) => {
                const gebunden = /<input\b[^>]*bind:this=\{(\w+)\}/s.exec(quelle);
                if (!gebunden) return true;
                // Der Name aus `bind:this` muss auch fokussiert werden — sonst hängt
                // die Referenz an einem Feld, das niemand anspricht.
                return !new RegExp(`${gebunden[1]}\\??\\.focus\\(\\)`).test(quelle);
            })
            .map(({ name }) => name);

        expect(
            fehlend,
            "Diese Dialoge nehmen Tastendrücke an einem <input> entgegen, holen den " +
                "Fokus aber nicht dorthin. Escape, Pfeiltasten und Enter sind damit " +
                "wirkungslos, und Getipptes landet im darunterliegenden Feld — ohne " +
                "dass man dem Dialog etwas ansieht.",
        ).toEqual([]);
    });

    it("behandelt Escape vor jedem vorzeitigen Abbruch", () => {
        // Im `AssistantPicker` stand die Escape-Behandlung unten im `switch` — also
        // hinter dem `return` für die leere Trefferliste. Wer sich vertippt hatte und
        // nichts fand, kam nicht mehr heraus. Geprüft wird die Reihenfolge im
        // Quelltext: Die Behandlung muss vor dem ersten `return` fallen.
        //
        // ⚠️ **Kommentare erst wegwerfen.** Die erste Fassung dieses Tests suchte
        // schlicht nach dem Wort im Funktionskörper — und fand den Kommentar, der
        // die Regel erklärt. Der Test war damit grün, während der Defekt wieder
        // eingebaut war (bemerkt bei der Gegenprobe am 10.09.2026). Derselbe
        // Fehlgriff wie bei der Wortsuche im Krisen-Mailtext, die über ihren
        // eigenen Erklärsatz stolperte: Ein Wächter darf nicht messen, was über ihn
        // geschrieben steht.
        const ohneKommentare = (text) =>
            text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

        const stolpernd = [];
        for (const { name, quelle } of tastaturkomponenten()) {
            const funktion = /function handleKeydown\([^)]*\)\s*\{/.exec(quelle);
            if (!funktion) continue;
            const koerper = ohneKommentare(quelle.slice(funktion.index));
            // Beide Schreibweisen zählen: `case 'Escape':` wie `e.key === 'Escape'`.
            const escape = koerper.search(/['"]Escape['"]/);
            const abbruch = koerper.search(/\breturn\b/);
            if (escape === -1) {
                stolpernd.push(`${name} (kein Escape)`);
            } else if (abbruch !== -1 && abbruch < escape) {
                stolpernd.push(`${name} (return vor Escape)`);
            }
        }
        expect(
            stolpernd,
            "Abbrechen muss immer gehen — gerade bei leerer Trefferliste, denn " +
                "genau dann will man heraus.",
        ).toEqual([]);
    });
});
