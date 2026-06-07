/**
 * Zerlegt einen reinen Text weiter in {kind:'text'} und {kind:'url'}-Parts.
 * URLs werden als klickbare Links gerendert — kein @html auf Roh-Freitext nötig.
 */
const URL_RE = /(https?:\/\/[^\s]+)/g

/**
 * @param {string} text
 * @returns {Array<{kind:'text'|'url', label:string, href?:string}>}
 */
export function linkifyText(text) {
    if (!text) return []
    const parts = []
    let last = 0
    for (const m of text.matchAll(URL_RE)) {
        if (m.index > last) {
            parts.push({ kind: 'text', label: text.slice(last, m.index) })
        }
        parts.push({ kind: 'url', label: m[1], href: m[1] })
        last = m.index + m[1].length
    }
    if (last < text.length) {
        parts.push({ kind: 'text', label: text.slice(last) })
    }
    return parts
}
