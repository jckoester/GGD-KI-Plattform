/**
 * PII-Gate-Logik (Phase 14, Datensparsamkeit) — Schritt 5.
 *
 * Führt die beiden Erkennungsschichten zusammen und bereitet sie für den
 * Bestätigungsdialog auf:
 *   1. Client-Regex (latenzfrei, strukturierte PII) — `pii_client.js`
 *   2. Server-NER (Name/Wohnort) — `POST /pii/scan`
 *
 * Die reinen Funktionen (`combinePiiSpans`, `segmentText`) sind ohne Netzwerk
 * testbar; `scanForPii` orchestriert beide Schichten.
 *
 * Charakter: Schutz-Nudge, **fail-open**. Fällt der Server-Scan aus ODER läuft er
 * in den Timeout, bleibt die Client-Schicht aktiv — die Eingabe wird nie hart
 * blockiert und hängt nie länger als `PII_SCAN_TIMEOUT_MS`.
 */

import { scanStructured } from "./pii_client.js";
import { scanPii } from "./api.js";

/**
 * Obergrenze für den Server-Scan. spaCy `md` braucht real ~Millisekunden; der
 * großzügige Wert greift nur, wenn das Backend tatsächlich hängt/überlastet ist —
 * dann fällt das Gate auf die Client-Schicht zurück, statt die Eingabe zu blockieren.
 */
export const PII_SCAN_TIMEOUT_MS = 1500;

/** @typedef {{category: string, start: number, end: number, text: string}} PiiSpan */

/** Anzeigelabel je Kategorie (Server: name/wohnort, Client: email/telefon/iban). */
export const PII_CATEGORY_LABELS = {
    name: "Name",
    wohnort: "Wohnort",
    email: "E-Mail",
    telefon: "Telefon",
    iban: "IBAN",
};

/**
 * Führt mehrere Span-Listen zu einer überschneidungsfreien, nach Position
 * sortierten Liste zusammen. Überlappt ein späterer Span einen bereits
 * akzeptierten, wird er verworfen (bei gleichem Start gewinnt der längere) —
 * so bleibt der Text eindeutig segmentierbar.
 *
 * @param {...(PiiSpan[]|null|undefined)} spanLists
 * @returns {PiiSpan[]}
 */
export function combinePiiSpans(...spanLists) {
    const all = spanLists.flat().filter(Boolean);
    all.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));
    /** @type {PiiSpan[]} */
    const kept = [];
    for (const s of all) {
        if (kept.some((k) => s.start < k.end && k.start < s.end)) continue;
        kept.push(s);
    }
    return kept;
}

/**
 * Zerlegt den Text in Segmente für die Markierung im Dialog: normale Text-Stücke
 * (`category: null`) und hervorgehobene PII-Stücke (`category` gesetzt).
 * Setzt sortierte, überschneidungsfreie Spans voraus (→ `combinePiiSpans`).
 *
 * @param {string} text
 * @param {PiiSpan[]} spans
 * @returns {Array<{text: string, category: string|null}>}
 */
export function segmentText(text, spans) {
    const segments = [];
    let pos = 0;
    for (const s of spans) {
        if (s.start > pos)
            segments.push({ text: text.slice(pos, s.start), category: null });
        segments.push({ text: text.slice(s.start, s.end), category: s.category });
        pos = s.end;
    }
    if (pos < text.length)
        segments.push({ text: text.slice(pos), category: null });
    return segments;
}

/**
 * Eindeutige Kategorien (in Reihenfolge des ersten Auftretens) — für die
 * Zusammenfassungs-Chips im Dialog.
 * @param {PiiSpan[]} spans
 * @returns {string[]}
 */
export function uniqueCategories(spans) {
    const seen = [];
    for (const s of spans) if (!seen.includes(s.category)) seen.push(s.category);
    return seen;
}

/**
 * Scannt einen Text über beide Schichten und liefert die kombinierten Spans.
 *
 * Die Client-Regex läuft immer (synchron, latenzfrei). Der Server-Scan ist
 * **fail-open** und durch einen Timeout begrenzt: Bei Fehler ODER Timeout bleibt
 * nur die Client-Erkennung — die Eingabe wird nie blockiert und hängt nie länger
 * als `timeoutMs`.
 *
 * @param {string} text
 * @param {{timeoutMs?: number}} [opts]
 * @returns {Promise<PiiSpan[]>}
 */
export async function scanForPii(text, { timeoutMs = PII_SCAN_TIMEOUT_MS } = {}) {
    const clientSpans = scanStructured(text);
    let serverSpans = [];

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await scanPii(text, { signal: controller.signal });
        serverSpans = res?.spans ?? [];
    } catch (err) {
        // fail-open: Timeout ODER Endpoint-Fehler → nur Client-Schicht
        if (err?.name === "AbortError") {
            console.warn(
                "Server-PII-Scan abgebrochen (Timeout) — nutze nur Client-Erkennung.",
            );
        } else {
            console.error(
                "Server-PII-Scan fehlgeschlagen — nutze nur Client-Erkennung:",
                err,
            );
        }
    } finally {
        clearTimeout(timer);
    }

    return combinePiiSpans(clientSpans, serverSpans);
}
