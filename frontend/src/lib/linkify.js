/**
 * Zerlegt einen reinen Text weiter in {kind:'text'} und {kind:'url'}-Parts.
 * URLs werden als klickbare Links gerendert — kein @html auf Roh-Freitext nötig.
 */
const URL_RE = /(https?:\/\/[^\s]+)/g
// Nachgestellte Satzzeichen gehören nicht zur URL (z. B. „… siehe https://x.de.")
// Klammern bleiben absichtlich erhalten — sie kommen in URLs vor (z. B. Wikipedia-Links).
const TRAILING_PUNCT = /[.,;:!?]+$/

/**
 * @param {string} text
 * @returns {Array<{kind:'text'|'url', label:string, href?:string}>}
 */
export function linkifyText(text) {
    if (!text) return []
    const parts = []
    let last = 0
    for (const m of text.matchAll(URL_RE)) {
        let url = m[1]
        let trailing = ''
        const t = url.match(TRAILING_PUNCT)
        if (t) {
            trailing = t[0]
            url = url.slice(0, -trailing.length)
        }
        if (m.index > last) {
            parts.push({ kind: 'text', label: text.slice(last, m.index) })
        }
        parts.push({ kind: 'url', label: url, href: url })
        if (trailing) {
            parts.push({ kind: 'text', label: trailing })
        }
        last = m.index + m[1].length
    }
    if (last < text.length) {
        parts.push({ kind: 'text', label: text.slice(last) })
    }
    return parts
}
