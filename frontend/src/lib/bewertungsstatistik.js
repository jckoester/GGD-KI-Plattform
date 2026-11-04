// Statistik der Antwortbewertung (0.31, Päckchen T): Daumen je Assistent oder Modell.
//
// Die Zahlen kommen aus `rating_counts` (Woche × Assistent × Modell × Rolle, ohne Person).

import { alsCsv } from "$lib/vorabstatistik.js";

/** Unter so vielen Bewertungen zeigt die Seite keinen Anteil — er wäre Zufall. */
export const MINDEST_FUER_ANTEIL = 10;

/** Der Anteil „hilfreich“ in Prozent, oder `null` unter der Mindestzahl. */
export function anteilHoch(plus, minus, mindest = MINDEST_FUER_ANTEIL) {
    const n = (plus ?? 0) + (minus ?? 0);
    if (n < mindest || n === 0) return null;
    return Math.round((100 * plus) / n);
}

/** Wie der Anteil in der Tabelle steht. */
export function anteilText(plus, minus, mindest = MINDEST_FUER_ANTEIL) {
    const wert = anteilHoch(plus, minus, mindest);
    return wert === null ? "—" : `${wert} %`;
}

/** Beide Rollen zusammen. */
export function gesamt(zeile) {
    return {
        plus: zeile.plus_schueler + zeile.plus_lehrkraft,
        minus: zeile.minus_schueler + zeile.minus_lehrkraft,
    };
}

/** Die Bezeichnung einer Zeile — auch für leere Schlüssel. */
export function zeilenName(zeile, gruppierung) {
    if (zeile.name) return zeile.name;
    if (gruppierung === "modell") return "Modell unbekannt";
    return zeile.schluessel === null ? "Ohne Assistent" : `Assistent ${zeile.schluessel}`;
}

export function bewertungCsv(zeilen, gruppierung) {
    return alsCsv(
        [gruppierung, "plus_schueler", "minus_schueler", "plus_lehrkraft", "minus_lehrkraft"],
        zeilen.map((z) => [zeilenName(z, gruppierung), z.plus_schueler, z.minus_schueler,
            z.plus_lehrkraft, z.minus_lehrkraft]),
    );
}
