// Wie das Budget Nutzer:innen erklärt wird.
//
// Seit dem Wochenmodell wird nichts zurückgesetzt: Das Guthaben **wächst** jede
// Unterrichtswoche. Die Oberfläche muss das sagen, sonst wirkt ein aufgebrauchtes Budget
// endgültig — und die Schülerin hört auf, das Werkzeug zu nutzen, obwohl am Montag wieder
// etwas da ist.
//
// Ferienwochen bekommen keine Zuteilung. Das ist kein Fehler, es muss nur dastehen.

/** Datum als „Mo, 15.09." — kurz genug für die Seitenleiste. */
function wochentag(iso) {
    const d = new Date(`${iso}T00:00:00`);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString("de-DE", {
        weekday: "short",
        day: "2-digit",
        month: "2-digit",
    });
}

function betrag(eur) {
    return typeof eur === "number" ? eur.toFixed(2).replace(".", ",") : null;
}

/**
 * Ein Satz, der sagt, wann und wie viel dazukommt.
 *
 * Gibt `null` zurück, wenn die Angaben fehlen — dann lässt die Oberfläche den Hinweis
 * weg, statt etwas Halbes zu behaupten. Der verbleibende Betrag steht ohnehin daneben.
 *
 * @param {{ wochenbetrag_eur?: number|null, naechste_aufstockung?: string|null }} b
 * @returns {string|null}
 */
export function zuwachsText(b) {
    const wochenbetrag = betrag(b?.wochenbetrag_eur);
    if (!wochenbetrag || b?.wochenbetrag_eur <= 0) return null;

    const tag = b?.naechste_aufstockung ? wochentag(b.naechste_aufstockung) : null;
    if (!tag) {
        // Kein Folgetermin: letzte Ferien des Schuljahres. Das offen zu sagen ist
        // ehrlicher als „wächst jede Woche" — diesmal eben nicht mehr.
        return "Bis zum Schuljahresende kommt kein Guthaben mehr dazu.";
    }
    // Ohne Schlusspunkt: Das Datum endet in de-DE bereits auf einen („Mo., 21.09."),
    // ein zweiter ergäbe „21.09...".
    return `Jede Unterrichtswoche kommen ${wochenbetrag} € dazu — das nächste Mal am ${tag}`;
}

/**
 * Wie viel sich höchstens ansammelt.
 *
 * Die Zahl steht in `budget_tiers.yaml` (`vorsprung_wochen`) — „einige Wochen" zu schreiben
 * hieße, eine konfigurierte Größe zu verschweigen. Mit dem Wochenbetrag daneben lässt sich
 * sogar der Euro-Betrag nennen, und das ist die Zahl, die man im Kopf behält.
 *
 * @param {{ wochenbetrag_eur?: number|null, vorsprung_wochen?: number|null }} b
 * @returns {string|null}
 */
export function uebertragText(b) {
    const wochen = b?.vorsprung_wochen;
    if (!Number.isFinite(wochen) || wochen < 1) return null;

    const wocheWort = wochen === 1 ? "einer Woche" : `${wochen} Wochen`;
    const grenze = betrag(b?.wochenbetrag_eur * wochen);

    // Ohne Wochenbetrag nur die Wochen nennen — halb ist besser als falsch.
    if (!grenze || !(b?.wochenbetrag_eur > 0)) {
        return `Ungenutztes bleibt dir erhalten, höchstens aber der Betrag von ${wocheWort}.`;
    }
    return `Ungenutztes bleibt dir erhalten — bis zu ${grenze} €, dem Betrag von ${wocheWort}. Mehr sammelt sich nicht an.`;
}

/**
 * Kurzform für die Seitenleiste, wo kein ganzer Satz hinpasst.
 * @returns {string|null}
 */
export function zuwachsKurz(b) {
    const wochenbetrag = betrag(b?.wochenbetrag_eur);
    if (!wochenbetrag || b?.wochenbetrag_eur <= 0) return null;
    const tag = b?.naechste_aufstockung ? wochentag(b.naechste_aufstockung) : null;
    return tag ? `+${wochenbetrag} € am ${tag}` : null;
}
