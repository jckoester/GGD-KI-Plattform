/**
 * Ist gegen Soll auf `/budget` — was das Diagramm zeigt (0.12, Paket 2, AP2).
 *
 * Die Hochrechnung stand bis 0.12 als Zahl da. Ihr Zweck ist der Zeitpunkt: Zeichnet
 * sich im März ab, dass nur ein Bruchteil der Zusage abfließt, kann die Schule die
 * Wochenbeträge fürs zweite Halbjahr anheben. Eine Linie zeigt das früher als eine Zahl.
 *
 * ⚠️ **Die Soll-Linie ist eine Treppe.** Sie wächst nur in Unterrichtswochen, in den
 * Ferien bleibt sie flach. Eine Gerade läge dort über der Wirklichkeit und würde die
 * Schule im Januar fälschlich beruhigen. Gezeichnet wird sie deshalb als Stufe
 * (`stepped`), und die x-Achse sind Kalenderwochen, keine Unterrichtswochen — nur so
 * sind die Ferien überhaupt als flache Stufe zu sehen.
 */

/** „2026-09-14" → „14.09." */
export function datumKurz(iso) {
    const [, monat, tag] = String(iso).split("-");
    return monat && tag ? `${tag}.${monat}.` : String(iso);
}

/**
 * Die beiden Reihen für chart.js. `null` im Ist für kommende Wochen — chart.js zeichnet
 * dort nichts, statt eine Null vorzutäuschen.
 * @param {{montag:string, soll_eur:number, ist_eur:number|null}[]} verlauf
 */
export function reihen(verlauf) {
    return {
        labels: (verlauf ?? []).map((p) => datumKurz(p.montag)),
        soll: (verlauf ?? []).map((p) => p.soll_eur),
        ist: (verlauf ?? []).map((p) => p.ist_eur),
    };
}

/** Lohnt ein Diagramm? Ohne eine einzige vergangene Woche zeigt es nur eine Treppe. */
export function zeigbar(verlauf) {
    return (verlauf ?? []).some((p) => p.ist_eur !== null && p.ist_eur !== undefined);
}

/** Betrag für Achse, Tooltip und Tabelle. */
export function euro(wert) {
    if (wert === null || wert === undefined) return "—";
    return wert.toLocaleString("de-DE", { style: "currency", currency: "EUR" });
}

/**
 * Zeilen der Tabellenansicht. Die Tabelle ist kein Zierrat: Tooltips **ergänzen**,
 * sie dürfen nicht der einzige Weg zu einem Wert sein (Tastatur, Bildschirmleser,
 * Ausdruck).
 */
export function tabellenZeilen(verlauf) {
    return (verlauf ?? []).map((p) => ({
        woche: datumKurz(p.montag),
        soll: euro(p.soll_eur),
        ist: euro(p.ist_eur),
        ferien: !p.unterricht,
    }));
}
