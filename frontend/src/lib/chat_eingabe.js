/**
 * Die Eingabezeile des Chats auf kleinem und berührbarem Bildschirm (0.15.1).
 *
 * Zwei Rückmeldungen aus der Beta: Auf dem iPad im Querformat nimmt die
 * Bildschirmtastatur etwa die Hälfte des Bildschirms, und was bleibt, teilen sich
 * Eingabebereich und Antwort — bei einer Rückfrage war die Antwort kaum noch zu lesen.
 * Und auf der Bildschirmtastatur schickt Enter die Nachricht ab, wo man eine neue Zeile
 * wollte.
 */

/** Unter dieser sichtbaren Höhe (CSS-Pixel) verdichtet sich der Eingabebereich.
 *
 * Gewählt nach den Geräten, um die es geht: iPad 11″ im Querformat mit offener Tastatur
 * lässt rund 300–350 px, iPad 13″ rund 500–530 px, ein Telefon im Hochformat rund
 * 400–450 px. Ein Desktopfenster liegt fast immer darüber. Dass die Höhe gemessen wird
 * und nicht die Tastatur erkannt, ist Absicht: Ein Browser verrät nicht verlässlich, ob
 * eine Bildschirmtastatur offen ist — knapp ist knapp, egal warum.
 */
export const KOMPAKT_UNTER_PX = 560;

/** Höchstzahl der Zeilen, auf die das Textfeld wächst. */
export const ZEILEN_MAX = 6;
export const ZEILEN_MAX_KOMPAKT = 3;

export function istKompakt(sichtbareHoehe) {
    return typeof sichtbareHoehe === "number" && sichtbareHoehe < KOMPAKT_UNTER_PX;
}

export function zeilenMax(kompakt) {
    return kompakt ? ZEILEN_MAX_KOMPAKT : ZEILEN_MAX;
}

// ── Enter-Taste ──────────────────────────────────────────────────────────────

/** Schlüssel in den Einstellungen (`user.preferences`). */
export const ENTER_SCHLUESSEL = "chat_enter";

export const ENTER_OPTIONEN = [
    {
        value: "auto",
        label: "Automatisch",
        hinweis:
            "Auf Touch-Geräten macht Enter eine neue Zeile, sonst sendet Enter.",
    },
    {
        value: "senden",
        label: "Enter sendet, Umschalt+Enter neue Zeile",
        hinweis: "Wie am Computer üblich.",
    },
    {
        value: "zeile",
        label: "Enter neue Zeile, Senden per Knopf",
        hinweis: "Gesendet wird mit dem Knopf.",
    },
];

/** Der eingestellte Modus; Unbekanntes und Fehlendes gilt als „auto". */
export function enterModus(preferences) {
    const wert = preferences?.[ENTER_SCHLUESSEL];
    return ENTER_OPTIONEN.some((o) => o.value === wert) ? wert : "auto";
}

/**
 * Schickt Enter (ohne Zusatztaste) ab?
 *
 * `beruehrung` heißt: Das Gerät hat keinen feinen Zeiger (`pointer: coarse`) — Telefon,
 * Tablet ohne Trackpad. Eine angeschlossene Hardware-Tastatur kann eine Webseite **nicht**
 * erkennen; ein iPad mit Tastaturhülle ohne Trackpad gilt deshalb als Touch-Gerät. Für
 * diesen Fall sendet Strg/⌘+Enter immer, und die Einstellung lässt sich festlegen.
 */
export function enterSendet(modus, beruehrung) {
    if (modus === "senden") return true;
    if (modus === "zeile") return false;
    return !beruehrung;
}

/**
 * Was ein Tastendruck im Textfeld auslöst: `"senden"` oder `null` (Standardverhalten,
 * bei Enter also eine neue Zeile).
 *
 * ⚠️ **Nicht während einer Eingabe über eine Eingabemethode** (`isComposing`, bei
 * manchen Browsern nur als `keyCode` 229 erkennbar): Bei chinesischer oder japanischer
 * Eingabe, auch bei manchen Android-Tastaturen, bestätigt Enter dort das Wort. Bis 0.15.0
 * schickte es die halbe Nachricht ab.
 */
export function tastenAktion(e, { modus, beruehrung }) {
    if (e.key !== "Enter" || e.isComposing || e.keyCode === 229) return null;
    if (e.metaKey || e.ctrlKey) return "senden";
    if (e.shiftKey || e.altKey) return null;
    return enterSendet(modus, beruehrung) ? "senden" : null;
}
