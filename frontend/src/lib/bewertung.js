// Antwortbewertung (0.31, Päckchen T, ADR-020): Daumen hoch/runter an einer Modellantwort.
//
// Die Regeln stehen hier, nicht im Bauteil — das Projekt hat keine Svelte-Komponententests.

/** Hilfreich / nicht hilfreich — Wert, Beschriftung für Screenreader und Tooltip. */
export const DAUMEN = [
    { wert: 1, label: "Hilfreich" },
    { wert: -1, label: "Nicht hilfreich" },
];

/**
 * Was ein Klick bewirkt: Derselbe Daumen noch einmal nimmt die Bewertung zurück (`0`), der
 * andere schaltet um.
 */
export function naechsteBewertung(aktuell, geklickt) {
    return aktuell === geklickt ? 0 : geklickt;
}

/** Der Wert, wie der Server ihn zurückgibt — `0` heißt „keine“. */
export function alsAnzeige(wert) {
    return wert === 1 || wert === -1 ? wert : null;
}

/**
 * Stehen an dieser Nachricht Daumen? Nur an fertigen, gespeicherten Antworten eines Chats,
 * der bewertbar ist (nicht Test, nicht Vorschau — das sagt der Server, Plan F6). Ohne `id`
 * ist die Antwort noch nicht gespeichert; leere Antworten (Abbruch vor dem ersten Wort)
 * bewertet niemand sinnvoll.
 */
export function zeigeDaumen({ bewertbar, message, isStreaming }) {
    return Boolean(
        bewertbar &&
            !isStreaming &&
            message?.role === "assistant" &&
            message?.id &&
            (message?.content ?? "").trim(),
    );
}
