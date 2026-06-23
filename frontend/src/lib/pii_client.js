/**
 * Client-seitige Sofort-Erkennung strukturierter PII (E-Mail, Telefon, IBAN).
 *
 * Erste, latenzfreie Schicht des PII-Eingabe-Gates (Phase 14, Datensparsamkeit):
 * läuft rein im Browser, ohne Round-Trip. Ergänzt die serverseitige NER für
 * Name (`PER`) und Wohnort (`LOC`) aus `POST /pii/scan`. Strukturierte PII liegt
 * bewusst NUR hier (Entscheidung D-C) — der Endpoint macht ausschließlich
 * Name/Wohnort.
 *
 * Liefert dieselbe Span-Form wie der Server, damit Schritt 5 beide Quellen ohne
 * Umformung zusammenführen kann: {category, start, end, text}.
 *
 * Kategorien: 'email' | 'telefon' | 'iban'.
 *
 * Charakter: Schutz-Nudge, kein Zwang. Lieber präzise als vollständig — eine
 * verpasste Nummer ist harmloser als wiederholte Fehlalarme bei harmlosen Zahlen.
 */

/** @typedef {{category: 'email'|'telefon'|'iban', start: number, end: number, text: string}} PiiSpan */

// E-Mail: bewusst pragmatisch (keine RFC-5322-Vollständigkeit). Lokalteil +
// Domain mit mind. einer Punkt-getrennten TLD aus Buchstaben.
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g

// IBAN: 2 Länder-Buchstaben + 2 Prüfziffern + 12–30 alphanumerische BBAN-Zeichen
// (DE = 18 Ziffern), optionale Einzel-Leerzeichen als 4er-Gruppierung erlaubt.
const IBAN_RE = /\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){12,30}\b/g

// Telefon (dt./international): Präfix +49 / 0049 / +<intl> / 0, danach mindestens
// sechs Ziffern­gruppen mit erlaubten Trennern (Leerzeichen, /, -, Klammern).
// Bewusst KEIN Punkt als Trenner → Datumsangaben wie 01.01.2020 matchen nicht.
// Lookbehind verhindert den Start mitten in einer längeren Ziffernfolge.
const PHONE_RE = /(?<!\d)(?:\+49|0049|\+\d{1,3}|0)(?:[\s/()-]?\d){6,}/g

/** Zählt die Ziffern in einem String. */
function digitCount(s) {
    const m = s.match(/\d/g)
    return m ? m.length : 0
}

/**
 * Baut Spans aus einem globalen Regex.
 * @param {string} text
 * @param {RegExp} re  globaler Regex
 * @param {PiiSpan['category']} category
 * @param {(match: string) => boolean} [accept]  optionaler Nachfilter
 * @returns {PiiSpan[]}
 */
function spansFrom(text, re, category, accept) {
    /** @type {PiiSpan[]} */
    const out = []
    for (const m of text.matchAll(re)) {
        const value = m[0]
        if (accept && !accept(value)) continue
        out.push({ category, start: m.index, end: m.index + value.length, text: value })
    }
    return out
}

/** Überlappen sich zwei Spans (halb-offene Intervalle)? */
function overlaps(a, b) {
    return a.start < b.end && b.start < a.end
}

/**
 * Scannt Text auf strukturierte PII (E-Mail, Telefon, IBAN).
 *
 * E-Mail und IBAN haben Vorrang vor Telefon: Eine IBAN enthält lange
 * Ziffernfolgen, die der Telefon-Heuristik ähneln — überlappende Telefon-Treffer
 * werden verworfen, damit derselbe Textbereich nicht doppelt markiert wird.
 *
 * @param {string} text
 * @returns {PiiSpan[]}  nach Startposition sortiert
 */
export function scanStructured(text) {
    if (!text) return []

    const emails = spansFrom(text, EMAIL_RE, 'email')
    const ibans = spansFrom(text, IBAN_RE, 'iban')
    // Telefonnummern haben 7–15 Ziffern (E.164-Obergrenze); das filtert kurze
    // Treffer und überlange Ziffern-Blöcke (z. B. fälschlich erkannte Codes) heraus.
    const phones = spansFrom(text, PHONE_RE, 'telefon', (v) => {
        const n = digitCount(v)
        return n >= 7 && n <= 15
    })

    const strong = [...emails, ...ibans]
    const keptPhones = phones.filter((p) => !strong.some((s) => overlaps(p, s)))

    return [...strong, ...keptPhones].sort((a, b) => a.start - b.start)
}
