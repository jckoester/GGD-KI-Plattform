/**
 * Vorab-Statistik unter `/statistics/vorab` (0.16) — Anteile, Kalenderwochen, Sortierung, CSV.
 *
 * „Nachgeschlagen" heißt: Der angebotene Knoten stand im Werkzeugergebnis derselben Antwort.
 * Ob das Modell ihn gezielt geholt hat oder er bei einer anderen Suche mitkam, sieht die
 * Statistik nicht — deshalb heißt die Quote nicht „Trefferquote".
 */

/** Die Zähler einer Wochenzeile, in der Reihenfolge der Tabelle. */
export const WOCHENZAEHLER = [
    "nachrichten",
    "mit_sicher",
    "mit_angebot",
    "angebot_nachgeschlagen",
    "angebot_ohne_sicher",
    "angebot_ohne_sicher_nachgeschlagen",
    "suchen_ohne_angebot",
];

/** „3/4 (75 %)" — ohne Nenner ein Strich, nie „0 %" aus nichts. */
export function anteil(teil, ganzes) {
    if (!ganzes) return "—";
    return `${teil}/${ganzes} (${Math.round((100 * teil) / ganzes)} %)`;
}

/** „KW 2/2030" aus dem Montag einer Woche (`YYYY-MM-DD`); das Jahr ist das der ISO-Woche. */
export function kalenderwoche(montag) {
    const [j, m, t] = montag.split("-").map(Number);
    const donnerstag = new Date(Date.UTC(j, m - 1, t + 3));
    const jahr = donnerstag.getUTCFullYear();
    const tag = (donnerstag - Date.UTC(jahr, 0, 1)) / 86400000;
    return `KW ${Math.floor(tag / 7) + 1}/${jahr}`;
}

/** Die Wochenzeilen aufsummiert — für die Zeile „Zeitraum". */
export function summe(wochen) {
    return Object.fromEntries(
        WOCHENZAEHLER.map((z) => [z, wochen.reduce((s, w) => s + (w[z] ?? 0), 0)]),
    );
}

/** Anteil nachgeschlagen je Knoten; ohne Angebot `null` (sortiert ans Ende). */
export function knotenanteil(k) {
    return k.angeboten ? k.nachgeschlagen / k.angeboten : null;
}

/**
 * Knoten sortiert nach ``schluessel`` (`sicher`, `angeboten`, `nachgeschlagen`, `anteil`),
 * absteigend; bei Gleichstand nach „angeboten", dann nach Titel. Neue Liste.
 */
export function sortiere(knoten, schluessel, absteigend = true) {
    const wert = (k) => (schluessel === "anteil" ? knotenanteil(k) : k[schluessel]);
    const richtung = absteigend ? -1 : 1;
    return [...knoten].sort((a, b) => {
        const wa = wert(a);
        const wb = wert(b);
        if (wa === null && wb !== null) return 1;
        if (wb === null && wa !== null) return -1;
        if (wa !== wb) return (wa < wb ? -1 : 1) * richtung;
        if (a.angeboten !== b.angeboten) return b.angeboten - a.angeboten;
        return (a.titel ?? "").localeCompare(b.titel ?? "", "de");
    });
}

function feld(wert) {
    const text = wert === null || wert === undefined ? "" : String(wert);
    return /[";\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/**
 * CSV für eine Tabellenkalkulation: Semikolon, CRLF und ein BOM vorn — so öffnet eine
 * deutsch eingestellte Tabellenkalkulation Umlaute und Spalten richtig.
 */
export function alsCsv(kopf, zeilen) {
    return "﻿" + [kopf, ...zeilen].map((z) => z.map(feld).join(";")).join("\r\n") + "\r\n";
}

export function wochenCsv(wochen) {
    return alsCsv(
        ["woche", ...WOCHENZAEHLER],
        wochen.map((w) => [w.woche, ...WOCHENZAEHLER.map((z) => w[z])]),
    );
}

export function knotenCsv(knoten) {
    return alsCsv(
        ["node_id", "titel", "fach", "sicher", "angeboten", "nachgeschlagen"],
        knoten.map((k) => [k.node_id, k.titel, k.fach, k.sicher, k.angeboten, k.nachgeschlagen]),
    );
}
