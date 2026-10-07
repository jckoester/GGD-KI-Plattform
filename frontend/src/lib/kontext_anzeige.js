/**
 * Die Zeile „Kontext (n)" unter einer Antwort (0.14) — was dort steht.
 *
 * Gezeigt wird, was beim Antworten **vorlag**, nicht was das Modell verwendet hat; deshalb
 * „Kontext" und nicht „Quellen" (Entscheidung Jan, 27.09.2026). Wie ausführlich, wählt
 * jede Person im Profil (`kontext_anzeige`), nicht die Rolle — wie bei der Kostenanzeige.
 */
import { getContextNode } from "./api.js";
import { HUELLE, alleAbbildungen, fuelleAbbildungen } from "./abbildungen.js";

export const KONTEXT_VORGABE = "kurz";

export const kontextStufenOptionen = [
    { value: "aus", label: "Gar nicht" },
    { value: "kurz", label: "Kurz: Titel und Fach" },
    { value: "ausfuehrlich", label: "Ausführlich: dazu Fundweg, Datum und Abbildungen" },
];

const STUFEN = kontextStufenOptionen.map((o) => o.value);

/** Die Stufe aus den Präferenzen; ein fehlender oder unbekannter Wert ist die Vorgabe. */
export function kontextStufe(preferences) {
    const wert = preferences?.kontext_anzeige;
    return STUFEN.includes(wert) ? wert : KONTEXT_VORGABE;
}

/**
 * Die Einträge unter einer Antwort — oder `null`, wenn dort **keine** Zeile hingehört.
 *
 * ⚠️ **Keine leere Zeile.** „Kontext (0)" sagte „dazu gab es keinen Kontext" — das stimmt
 * nur, wenn tatsächlich gesucht wurde, und für Antworten von vor 0.14 stimmt es nie.
 * Während des Streams auch nichts: Die Liste kommt erst nach dem Speichern.
 */
export function kontextEintraege(message, stufe, isStreaming = false) {
    if (stufe === "aus" || isStreaming) return null;
    const bausteine = message?.kontext ?? [];
    if (!bausteine.length) return null;
    return bausteine.map((b) => ({
        node_id: b.node_id,
        // Wie der Dateiname eines Begriffs: „Oxidation (Elektronenabgabe)".
        titel: b.fassung ? `${b.title} (${b.fassung})` : b.title,
        fach: b.fach ?? null,
        href: `/knowledge/${b.node_id}`,
        details: stufe === "ausfuehrlich" ? details(b) : [],
        // Nur ausführlich (Entscheidung Jan, 27.09.2026) — und geladen wird erst, wenn
        // die Liste aufgeklappt ist, also die Komponente steht.
        abbildungen: stufe === "ausfuehrlich" && !!b.hat_abbildungen,
    }));
}

function details(b) {
    const teile = [];
    if (b.herkunft === "werkzeug") teile.push("vom Assistenten nachgeschlagen");
    else teile.push("vorab zur Frage gefunden");
    // Eine Ähnlichkeit hat nur ein thematischer Treffer. Ein Vorab-Treffer ohne sie kam
    // über den Namen — er ist nicht ähnlich, er heißt so.
    if (b.aehnlichkeit != null) teile.push(`Ähnlichkeit ${komma(b.aehnlichkeit)}`);
    else if (b.herkunft === "vorab") teile.push("über den Namen");
    const datum = tag(b.updated_at);
    if (datum) teile.push(`geändert am ${datum}`);
    return teile;
}

function komma(zahl) {
    return zahl.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function tag(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// ── Abbildungen (Schritt 4) ─────────────────────────────────────────────────

const geladen = new Map();

/**
 * Die Abbildungen eines Bausteins, die sich zeigen lassen (mit SVG) — einmal je Knoten
 * und Seitenaufruf geholt. Wer dieselbe Liste auf- und zuklappt oder denselben Baustein
 * unter zwei Antworten hat, löst keine zweite Anfrage aus.
 *
 * Ein Fehler (Knoten inzwischen weg, Netz) heißt „keine Abbildungen" und wird nicht
 * gemerkt: Beim nächsten Aufklappen wird es noch einmal versucht.
 */
export function ladeAbbildungen(nodeId, holen = getContextNode) {
    if (!geladen.has(nodeId)) {
        geladen.set(nodeId, holen(nodeId)
            .then((node) => alleAbbildungen(node).filter((abb) => abb?.svg))
            .catch(() => {
                geladen.delete(nodeId);
                return [];
            }));
    }
    return geladen.get(nodeId);
}

/** Nur für Tests: den Zwischenspeicher leeren. */
export function vergiss() {
    geladen.clear();
}

/**
 * Die Abbildungen unter `wurzel` setzen — je eine Hülle, gefüllt von derselben Funktion
 * wie in der Detailansicht (`fuelleAbbildungen`).
 *
 * ⚠️ **Nicht selbst `innerHTML` setzen.** Das SVG stammt aus einem Vault und ist
 * ungeprüft; die Sanitisierung steckt in `fuelleAbbildungen`, und nur dort — eine
 * zweite Stelle mit eigenem DOMPurify-Profil wäre die Drift, vor der `abbildungen.js`
 * warnt (Phase 17: eine eigene `ALLOWED_URI_REGEXP` strich das `d`-Attribut).
 */
export function zeigeAbbildungen(wurzel, abbildungen) {
    if (!wurzel) return;
    wurzel.replaceChildren(
        ...(abbildungen ?? []).map((abb) => {
            const huelle = document.createElement("span");
            huelle.className = HUELLE;
            huelle.dataset.datei = abb.datei;
            return huelle;
        }),
    );
    fuelleAbbildungen(wurzel, abbildungen);
}
