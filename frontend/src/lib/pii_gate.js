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
 * Charakter: Schutz-Nudge, **fail-open**. Fällt der Server-Scan aus, bleibt die
 * Client-Schicht aktiv — die Eingabe wird nie hart blockiert. (Timeout-Härtung in
 * Schritt 6.)
 */

import { scanStructured } from "./pii_client.js";
import { scanPii } from "./api.js";

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
 * Der Server-Scan ist **fail-open**: schlägt er fehl, bleibt nur die
 * Client-Erkennung — die Eingabe wird nie blockiert.
 *
 * @param {string} text
 * @returns {Promise<PiiSpan[]>}
 */
export async function scanForPii(text) {
    const clientSpans = scanStructured(text);
    let serverSpans = [];
    try {
        const res = await scanPii(text);
        serverSpans = res?.spans ?? [];
    } catch (err) {
        // fail-open: nur Client-Schicht; Eingabe nicht hart blockieren
        console.error(
            "Server-PII-Scan fehlgeschlagen — nutze nur Client-Erkennung:",
            err,
        );
    }
    return combinePiiSpans(clientSpans, serverSpans);
}
