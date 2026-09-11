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

// ── Antwort ohne Inhalt ─────────────────────────────────────────────────────

/**
 * Hat eine fertige Assistenten-Antwort **gar nichts** hervorgebracht?
 *
 * **Der stille Ausfall, den das sichtbar macht.** Liefert das Modell eine leere
 * Completion, schreibt das Backend eine Assistenten-Nachricht der Länge 0. Die
 * Blase prüfte `{#if message.content || isStreaming}` — und rendert bei leerem
 * Inhalt schlicht *nichts*. Aus Nutzersicht: Man schickt eine Frage weg, es tut
 * sich nichts, und das Budget ist trotzdem belastet. Kein Fehler, keine Meldung,
 * keine Spur.
 *
 * ⚠️ **Bilder sind eine Antwort.** Erzeugt der Zug ein Bild, ohne Text zu
 * schreiben, ist die Nachricht inhaltsleer, aber nicht antwortlos — sie wird an
 * anderer Stelle gerendert. Wer das übersieht, hängt an jedes erzeugte Bild einen
 * Fehlalarm.
 *
 * Während des Streams gilt nichts als leer: Da ist der Inhalt nur noch nicht da.
 *
 * @param {{content?: string|null, images?: Array}|null} message
 * @param {boolean} isStreaming
 */
export function istLeereAntwort(message, isStreaming = false) {
    if (!message || isStreaming) return false;
    if (message.content) return false;
    return !(message.images?.length);
}

/**
 * Der Satz für eine leere Antwort — mit Kostenhinweis, wenn etwas gebucht wurde.
 *
 * Das Budget zu verschweigen wäre die zweite Hälfte desselben Fehlers: Die Anfrage
 * *hat* gekostet, auch ohne Ergebnis.
 *
 * @param {string|null} costEur  bereits formatierter Betrag oder `null`
 */
export function leereAntwortText(costEur = null) {
    const basis =
        "Das Modell hat diesmal nichts geantwortet. Das kommt gelegentlich vor — " +
        "schick die Frage einfach noch einmal ab.";
    return costEur !== null
        ? `${basis} Die Anfrage wurde trotzdem berechnet (${costEur} €).`
        : basis;
}
