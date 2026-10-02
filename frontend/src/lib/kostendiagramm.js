/**
 * Kostendiagramm unter `/statistics/costs` — Formatierung und Tabellenansicht.
 *
 * Hier bleibt der **Euro** die Einheit (Verwaltung und Schulleitung, gegen die
 * Anbieterrechnung prüfbar — Entscheidung zu AP4). Weil ein einzelner Tag oder eine
 * Woche aber leicht unter einem Cent liegt, zeigt der Betrag unter einem Euro bis zu vier
 * Nachkommastellen: „0,00 €" wäre derselbe Fehler, den die Einheiten für Nutzer:innen
 * behoben haben.
 */

/** Kleinster Betrag, den vier Nachkommastellen noch zeigen. */
const KLEINSTER = 0.0001;

/**
 * Betrag in deutscher Schreibweise; unter 1 bis zu vier Nachkommastellen.
 * Was darunter liegt, aber über null, heißt „< 0,0001 €" — nie „0,00 €".
 */
export function betrag(wert, waehrung = "€") {
    if (wert === null || wert === undefined) return "—";
    if (wert > 0 && wert < KLEINSTER / 2) {
        return `< ${KLEINSTER.toLocaleString("de-DE", { maximumFractionDigits: 4 })} ${waehrung}`;
    }
    const stellen = Math.abs(wert) < 1 ? 4 : 2;
    const zahl = wert.toLocaleString("de-DE", {
        minimumFractionDigits: 2,
        maximumFractionDigits: stellen,
    });
    return `${zahl} ${waehrung}`;
}

/**
 * Zeilen der Tabellenansicht — dieselben Werte wie im Tooltip, ohne ihn zu brauchen.
 * @param {{period:string, eur:number, usd:number}[]} eintraege
 */
export function tabellenZeilen(eintraege) {
    return (eintraege ?? []).map((e) => ({
        periode: e.period,
        eur: betrag(e.eur, "€"),
        usd: betrag(e.usd, "$"),
    }));
}
