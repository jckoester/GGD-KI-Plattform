/**
 * Trenner „Modell: …“ zwischen zwei Antworten (Aufgaben-Weiterleitung, Plan „Freier
 * Schüler-Chat“, 7a): Verglichen wird das **gewählte** Modell, nicht das antwortende. Leitet der
 * Klassifikator einen Zug an ein stärkeres Modell weiter, trägt die Antwort das Ausgangsmodell in
 * `weitergeleitetVon` — ein solcher Wechsel bekommt keinen Trenner, ein selbst gewählter schon.
 */

/** Das Modell, das die Person gewählt hatte; ohne Weiterleitung das antwortende. */
export function gewaehltesModell(nachricht) {
    return nachricht?.weitergeleitetVon || nachricht?.model || null;
}

/** Hat sich die Wahl zwischen der vorigen und dieser Antwort geändert? */
export function modellGewechselt(vorige, nachricht) {
    const jetzt = gewaehltesModell(nachricht);
    return Boolean(vorige && jetzt && jetzt !== gewaehltesModell(vorige));
}

/** `weitergeleitetVon` aus den Kopfzeilen der laufenden Antwort. */
export function weitergeleitetAus(antwortend, gewaehlt) {
    return gewaehlt && antwortend && gewaehlt !== antwortend ? gewaehlt : null;
}
