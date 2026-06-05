/**
 * Parser und Serializer für die Hinweise-Token-Notation.
 *
 * Token-Notation (round-trip-stabil):
 *   Leitperspektive : @[<Label>](lp:<uuid>)
 *   Cross-Fach-IK   : #[<Label>](ik:<uuid>)
 *   Alles andere    : unveränderter Freitext
 */

const LP_TOKEN  = /@\[([^\]]*)\]\(lp:([0-9a-f-]{36})\)/g
const IK_TOKEN  = /#\[([^\]]*)\]\(ik:([0-9a-f-]{36})\)/g
const ANY_TOKEN = /(@\[[^\]]*\]\(lp:[0-9a-f-]{36}\)|#\[[^\]]*\]\(ik:[0-9a-f-]{36}\))/g

/**
 * Zerlegt einen Hinweise-Text in Parts.
 * @param {string} text
 * @returns {Array<{kind:'text'|'lp'|'ik', label:string, node_id:string|null, raw:string}>}
 */
export function parseHinweise(text) {
    if (!text) return []

    const parts = []
    let last = 0

    for (const m of text.matchAll(ANY_TOKEN)) {
        // Text vor dem Token
        if (m.index > last) {
            parts.push({ kind: 'text', label: text.slice(last, m.index), node_id: null, raw: text.slice(last, m.index) })
        }

        const token = m[0]
        const lpMatch = token.match(/^@\[([^\]]*)\]\(lp:([0-9a-f-]{36})\)$/)
        const ikMatch = token.match(/^#\[([^\]]*)\]\(ik:([0-9a-f-]{36})\)$/)

        if (lpMatch) {
            parts.push({ kind: 'lp', label: lpMatch[1], node_id: lpMatch[2], raw: token })
        } else if (ikMatch) {
            parts.push({ kind: 'ik', label: ikMatch[1], node_id: ikMatch[2], raw: token })
        }

        last = m.index + token.length
    }

    // Restlicher Text
    if (last < text.length) {
        parts.push({ kind: 'text', label: text.slice(last), node_id: null, raw: text.slice(last) })
    }

    return parts
}

/**
 * Baut aus einem Parts-Array wieder einen String zusammen.
 * @param {Array<{kind:string, label:string, node_id:string|null}>} parts
 * @returns {string}
 */
export function serializeHinweise(parts) {
    return parts.map(p => {
        if (p.kind === 'lp')  return `@[${p.label}](lp:${p.node_id})`
        if (p.kind === 'ik')  return `#[${p.label}](ik:${p.node_id})`
        return p.label ?? p.raw ?? ''
    }).join('')
}

/**
 * Extrahiert Kanten-Ziel-UUIDs aus einem Hinweise-Text.
 * @param {string} text
 * @returns {{ lp: string[], ik: string[] }}
 */
export function extractEdgeTargets(text) {
    if (!text) return { lp: [], ik: [] }
    const lp = [...text.matchAll(/@\[[^\]]*\]\(lp:([0-9a-f-]{36})\)/g)].map(m => m[1])
    const ik = [...text.matchAll(/#\[[^\]]*\]\(ik:([0-9a-f-]{36})\)/g)].map(m => m[1])
    return { lp, ik }
}
