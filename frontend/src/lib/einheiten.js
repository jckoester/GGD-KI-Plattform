/**
 * Die **Einheit** für Kosten — 1 Einheit = 1/10 000 € (ein Hundertstelcent).
 *
 * **Warum nicht Euro.** Eine Nachricht kostet rund 0,0007 €. Die Anzeige wich deshalb
 * unter einem Cent auf „< 0,01 €" aus — und **97,7 % aller erfassten Nachrichten
 * zeigten denselben Text** (gemessen 29.09.2026 an 474 Nachrichten). Eine Angabe, die
 * 0,001 € nicht von 0,009 € unterscheidet, ist keine Auskunft, sondern eine Stelle, an
 * der man aufhört hinzusehen.
 *
 * **Es ist keine erfundene Währung,** sondern eine Zehnerpotenz-Unterteilung des Euro.
 * Der Kurs steht in der Oberfläche; der Euro bleibt für Verwaltung und Schulleitung
 * (`/budget`, `/statistics/costs`) die Einheit, gegen die Anbieterrechnung prüfbar.
 *
 * ⚠️ **Gerechnet wird aus USD, nicht aus den `*_eur`-Feldern.** Die sind serverseitig
 * auf Cent gerundet — und ein Cent sind 100 Einheiten. Aus ihnen umzurechnen hieße,
 * die Auflösung wegzuwerfen, derentwegen es die Einheit gibt.
 *
 * ⚠️ **Der Feind ist nicht der Bruch, sondern die Null.** Was etwas gekostet hat, darf
 * nie als „0" erscheinen — das war der Euro-Fehler. Unter einer Einheit wird deshalb
 * mit einer Nachkommastelle gezeigt, und ein Betrag größer null niemals als 0.
 */

/** Vorgabe, falls der Server den Faktor (noch) nicht mitgeliefert hat. */
export const EINHEITEN_JE_EURO = 10000;

/**
 * **Das Anzeigewort — die einzige Stelle, an der es steht.**
 *
 * Wer es ändern will, ändert es hier; `text()` und `kurshinweis()` folgen, und die
 * Tests prüfen gegen diese Konstante statt gegen ein Literal. Der
 * Konfigurationsschlüssel (`einheiten_je_euro`) und die Bezeichner im Code bleiben
 * bewusst, wie sie sind: Geändert wird nur, was Menschen lesen — dieselbe Trennung wie
 * bei Werkzeug/Fähigkeit/Funktion (CLAUDE.md).
 *
 * ⚠️ **Offen:** „Einheit" ist in der Oberfläche bereits besetzt — als
 * *Unterrichtseinheit* in der Jahresplanung („Laufende Einheit", „Erst einer Einheit
 * zuordnen"), in zwölf Dateien unter `planner/` und `app/planning/`. Dass hier
 * dasselbe Wort für Kosten steht, ist eine bekannte Kollision; sie zu beheben ist seit
 * dieser Konstante eine Zeile.
 */
export const BEZEICHNUNG = { singular: "Einheit", plural: "Einheiten" };

/**
 * USD → Einheiten. `null`, wenn eine der Angaben fehlt.
 * @param {number|null|undefined} usd
 * @param {number|null|undefined} kurs   EUR→USD-Kurs
 * @param {number} [faktor]
 */
export function ausUsd(usd, kurs, faktor = EINHEITEN_JE_EURO) {
    if (usd === null || usd === undefined || !kurs || !faktor) return null;
    return (usd / kurs) * faktor;
}

/**
 * EUR → Einheiten. Für Beträge, die **in Euro** konfiguriert sind (Wochenbudgets aus
 * `budget_tiers.yaml`) — dort gibt es keine Rundung zu umgehen.
 * @param {number|null|undefined} eur
 * @param {number} [faktor]
 */
export function ausEuro(eur, faktor = EINHEITEN_JE_EURO) {
    if (eur === null || eur === undefined || !faktor) return null;
    return eur * faktor;
}

/**
 * Eine Zahl Einheiten als Text — ohne Einheitenwort.
 *
 * Ganze Zahlen ab 1, darunter eine Nachkommastelle, und niemals „0" für etwas, das
 * etwas gekostet hat.
 * @param {number|null} wert
 */
export function zahl(wert) {
    if (wert === null || wert === undefined) return null;
    if (wert === 0) return "0";
    if (wert < 0.05) return "<0,1";
    if (wert < 1) return wert.toLocaleString("de-DE", { maximumFractionDigits: 1 });
    return Math.round(wert).toLocaleString("de-DE");
}

/**
 * Fertiger Text mit Einheitenwort, z. B. „8 Einheiten" oder „1 Einheit".
 * @param {number|null} wert
 */
export function text(wert) {
    const z = zahl(wert);
    if (z === null) return null;
    return `${z} ${z === "1" ? BEZEICHNUNG.singular : BEZEICHNUNG.plural}`;
}

/**
 * Der Hinweis auf den Kurs — gehört sichtbar in die Oberfläche, nicht nur in die Doku.
 * @param {number} [faktor]
 */
export function kurshinweis(faktor = EINHEITEN_JE_EURO) {
    return `${faktor.toLocaleString("de-DE")} ${BEZEICHNUNG.plural} = 1 €`;
}
