/**
 * Was im Modellwähler über ein Modell steht — und was bewusst **nicht**.
 *
 * Bis 0.12 stand dort eine Liste von Namen und ein Zahnrad. Wer einen Assistenten
 * anlegt, hatte damit keine Entscheidungshilfe: Welches Modell ist teuer, welches kann
 * Werkzeuge, wie viel Vorgeschichte verträgt es?
 *
 * ⚠️ **`null` heißt unbekannt, nicht „nein".** Beim Kontextfenster ist das der
 * Regelfall: Gemessen am 29.09.2026 melden 17 von 31 Deployments eine Größe — **keines**
 * der IONOS-Modelle, weil LiteLLM sie nur für Modelle seiner eingebauten Tabelle kennt.
 * Eine Oberfläche, die daraus „0 Token" oder „kann keine Werkzeuge" macht, erfindet eine
 * Auskunft. Unbekanntes wird deshalb weggelassen, nicht verneint.
 */

import { ausUsd, zahl as einheitenZahl, BEZEICHNUNG } from "./einheiten.js";

/** Münze für die Kosten, Zahnrad für die Werkzeuge — die Marken im Auswahlfeld. */
export const MARKE_KOSTEN = "🪙";
export const MARKE_WERKZEUGE = "⚙";

/**
 * Die kompakte Kostenmarke für den Eintrag im Auswahlfeld — „~7 🪙" oder `null`.
 *
 * Kurz, weil ein `<option>` keine Gestaltung erlaubt und der Name lesbar bleiben muss.
 * ⚠️ **Die Münze ist nicht Zierde, sondern die Bedeutung:** „~7" allein sagt nicht,
 * wovon sieben — Jan, 01.10.2026: „es ist nicht klar, was das bedeuten soll". Das
 * Einheitenwort auszuschreiben macht den Eintrag zu lang; die vollen Angaben stehen
 * im Assistenten-Editor unter dem Feld.
 *
 * Die Tilde bleibt: Es ist eine Schätzung an einer mittleren Nachricht.
 */
export function kostenMarke(modell, kurs, faktor) {
    const einheiten = ausUsd(modell?.usd_je_nachricht, kurs, faktor);
    const z = einheitenZahl(einheiten);
    // Münze **hinter** die Zahl (Jan, 01.10.2026): So liest man erst den Wert und
    // dann, worum es sich handelt — wie bei „7 €", nicht wie bei „€ 7".
    return z === null ? null : `~${z} ${MARKE_KOSTEN}`;
}

/**
 * Beschriftung eines Eintrags im Auswahlfeld.
 *
 * Das Zahnrad stand hier schon vor 0.12 und ist der einzige Fähigkeitshinweis im
 * **Chat**-Wähler — dort gibt es keine Angabenzeile darunter.
 */
export function eintragsText(modell, kurs, faktor) {
    const teile = [modell?.label || modell?.id || ""];
    const marke = kostenMarke(modell, kurs, faktor);
    if (marke) teile.push(marke);
    if (modell?.supports_function_calling === true) teile.push(MARKE_WERKZEUGE);
    return teile.join(" · ");
}

/**
 * Die Angaben zum **gewählten** Modell, als Liste für die Zeile unter dem Auswahlfeld.
 *
 * Nur, was bekannt ist. Eine leere Liste ist eine gültige Antwort — dann schweigt die
 * Oberfläche, so wie vor 0.12.
 */
export function angaben(modell, kurs, faktor) {
    if (!modell) return [];
    const liste = [];

    const einheiten = ausUsd(modell.usd_je_nachricht, kurs, faktor);
    const z = einheitenZahl(einheiten);
    if (z !== null) {
        liste.push({
            was: "Kosten",
            wert: `etwa ${z} ${BEZEICHNUNG.plural} je Nachricht`,
        });
    }
    if (modell.kontextfenster) {
        liste.push({ was: "Kontextfenster", wert: tokenKurz(modell.kontextfenster) });
    }
    if (modell.supports_function_calling === true) {
        liste.push({ was: "Werkzeuge", wert: "ja" });
    } else if (modell.supports_function_calling === false) {
        // Hier ist das „nein" belegt und wichtig: Ohne Werkzeuge fallen Wissensspeicher
        // und Unterrichtsplanung aus — das soll man **vor** der Wahl sehen.
        liste.push({ was: "Werkzeuge", wert: "nein" });
    }
    if (modell.denkt === true) liste.push({ was: "Denkt vor der Antwort", wert: "ja" });
    if (modell.bilder === true) liste.push({ was: "Versteht Bilder", wert: "ja" });
    return liste;
}

/** 128000 → „128.000 Token (ca. 190 Seiten)". */
export function tokenKurz(token) {
    if (!token) return null;
    // Grobe Umrechnung: ~1,5 Token je Wort, ~450 Wörter je Seite. Die Seitenzahl ist
    // die Größe, die man sich vorstellen kann — die Tokenzahl die, die stimmt.
    const genau = token / 1.5 / 450;
    const zahl = token.toLocaleString("de-DE");
    // ⚠️ Vor dem Runden vergleichen: 500 Token sind 0,74 Seiten — gerundet „1", und
    // „ca. 1 Seiten" ist zweimal falsch (Aussage und Grammatik).
    if (genau < 1) return `${zahl} Token`;
    const seiten = Math.round(genau);
    const wort = seiten === 1 ? "Seite" : "Seiten";
    return `${zahl} Token (ca. ${seiten.toLocaleString("de-DE")} ${wort})`;
}
