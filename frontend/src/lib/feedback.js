// Die Regeln des Rückmelde-Formulars (ADR-020) — als Modul, nicht im Bauteil.
//
// Das Projekt hat keine Svelte-Komponententests (siehe `picker_tastatur.test.js`).
// Was sich prüfen lassen soll, steht deshalb hier: der Zuschnitt der Nutzlast, die
// Längengrenzen und die Beschriftungen. Das Bauteil rendert nur noch.

/** Muss mit `MIN_LAENGE`/`MAX_LAENGE` in `app/feedback/schemas.py` übereinstimmen. */
export const MIN_LAENGE = 20;
export const MAX_LAENGE = 4000;
export const MAX_KONTAKT = 200;

export const KATEGORIEN = [
    { wert: "bug", label: "Fehler" },
    { wert: "suggestion", label: "Verbesserungsvorschlag" },
    { wert: "other", label: "Sonstiges" },
];

/**
 * Der technische Kontext, den der Client von sich aus beilegt.
 *
 * **Warum automatisch.** „Welche Version, welche Seite, welcher Browser" beantwortet
 * niemand zuverlässig von Hand — und ohne diese drei Angaben ist eine Fehlermeldung
 * oft nicht nachvollziehbar. Die Query des Pfades bleibt draußen; sie kann tragen,
 * was in einer Meldung nichts zu suchen hat (eine Suchanfrage etwa). Der Server
 * kürzt sie zusätzlich — hier ist es eine Frage der Datensparsamkeit, dort eine der
 * Feldlänge.
 */
export function sammleKontext({ pfad, assistentId = null, version, fenster, kennung } = {}) {
    return {
        app_version: version ?? "unbekannt",
        route: (pfad ?? "").split("?")[0].split("#")[0] || null,
        assistant_id: assistentId ?? null,
        user_agent: kennung ?? null,
        viewport: fenster ?? null,
    };
}

/** Die Nutzlast für `POST /feedback`. */
export function baueNutzlast({ kategorie, text, kontakt = "", chatId = null, kontext = {} }) {
    return {
        category: kategorie,
        content: (text ?? "").trim(),
        contact: (kontakt ?? "").trim() || null,
        attach_conversation_id: chatId ?? null,
        ...kontext,
    };
}

/** Wie viele Zeichen noch fehlen — `0`, sobald abgeschickt werden kann. */
export function fehlendeZeichen(text) {
    return Math.max(0, MIN_LAENGE - (text ?? "").trim().length);
}

export function istAbsendbar(text) {
    const laenge = (text ?? "").trim().length;
    return laenge >= MIN_LAENGE && laenge <= MAX_LAENGE;
}

/**
 * Was unter „Meine Meldungen" am Eintrag steht.
 *
 * `spam` taucht hier nicht auf: Der Server liefert Meldenden dafür `declined` ohne
 * Begründung (ADR-020). Stünde die Marke doch einmal hier, wäre die Maskierung im
 * Backend gebrochen — dann ist „Nicht umgesetzt" immer noch die richtige Anzeige.
 */
export function statusText(eintrag) {
    switch (eintrag?.status) {
        case "open":
            return "Offen";
        case "in_progress":
            return "In Bearbeitung";
        case "done":
            return eintrag.resolved_in_version
                ? `Erledigt in ${eintrag.resolved_in_version}`
                : "Erledigt";
        default:
            return "Nicht umgesetzt";
    }
}

/** Die Farbrolle des Status-Abzeichens — semantische Tokens, keine rohen Werte. */
export function statusFarbe(status) {
    switch (status) {
        case "done":
            return "bg-light-gr-bg dark:bg-dark-gr-bg border-light-gr dark:border-dark-gr";
        case "in_progress":
            return "bg-light-bl-bg dark:bg-dark-bl-bg border-light-bl dark:border-dark-bl";
        case "open":
            return "bg-light-ye-bg dark:bg-dark-ye-bg border-light-ye dark:border-dark-ye";
        default:
            return "bg-light-ui-2 dark:bg-dark-ui-2 border-light-ui-3 dark:border-dark-ui-3";
    }
}

export function kategorieText(wert) {
    return KATEGORIEN.find((k) => k.wert === wert)?.label ?? wert;
}

/**
 * Der Satz, der bei einem Fehlschlag erscheint.
 *
 * Wie im Chat gilt: **Was das Backend sagt, gilt.** Sperre (403) und Limit (429)
 * schicken einen fertigen, für Nutzer:innen geschriebenen Satz mit — ihn durch einen
 * eigenen zu ersetzen, nähme die einzige Auskunft darüber weg, wie lange es dauert.
 */
export function feedbackFehlertext(err) {
    const eigener = err?.message;
    if (typeof eigener === "string" && eigener.trim()) return eigener;
    return "Die Meldung konnte nicht gesendet werden.";
}
