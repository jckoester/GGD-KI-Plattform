// Fehlermeldungen im Chat — welcher Satz erscheint, wenn eine Anfrage scheitert.
//
// Die Regel: **Was das Backend sagt, gilt.** Es kennt die Ursache, die Oberfläche nicht.
// Nur wo es nichts mitschickt (Netzwerkabbruch) oder nur Technisches (502/503), setzt
// diese Datei einen lesbaren Satz ein.
//
// ⚠️ Früher stand hier `429: "Dein Budget ist erschöpft."` — fest verdrahtet am Status.
// Das war in beide Richtungen falsch:
//   * Eine bloße Drosselung (`rate_limits.yaml`, auch 429) meldete ein erschöpftes Budget.
//   * Das echte Budgetende kam als **400** (LiteLLM 1.83.7) und wurde nie erkannt; die
//     Nutzerin sah stattdessen den rohen Fehlerkörper des Proxys.
// Deshalb hat 429 hier keinen Eintrag mehr: Beide Fälle unterscheidet nur das Backend.

/** Sätze für Fälle, in denen das Backend nichts Verwertbares mitschicken kann. */
const OHNE_AUSKUNFT = {
    0: "Verbindung zum Server fehlgeschlagen.",
    502: "Der KI-Dienst ist gerade nicht erreichbar.",
    503: "Der KI-Dienst ist vorübergehend nicht verfügbar.",
};

/**
 * Wählt den Satz, der in der Fehlerblase steht.
 *
 * @param {{ status?: number, message?: string }} err — in der Regel ein `ApiError`
 * @returns {string}
 */
export function chatFehlertext(err) {
    const vorgabe = OHNE_AUSKUNFT[err?.status];
    if (vorgabe) return vorgabe;
    const eigener = err?.message;
    return typeof eigener === "string" && eigener.trim()
        ? eigener
        : "Ein unbekannter Fehler ist aufgetreten.";
}
