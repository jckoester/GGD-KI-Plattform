/**
 * Parser und Serializer für die Material-Token-Notation.
 *
 * Token-Notation: @[<Label>](node:<uuid>)
 * Alles andere:   unveränderter Freitext
 */

const NODE_TOKEN = /@\[([^\]]*)\]\(node:([0-9a-f-]{36})\)/g

/**
 * Zerlegt einen Material-Text in Parts.
 * @param {string} text
 * @returns {Array<{kind:'text'|'node', label:string, node_id:string|null, raw:string}>}
 */
export function parseMaterial(text) {
    if (!text) return []
    const parts = []
    let last = 0
    for (const m of text.matchAll(NODE_TOKEN)) {
        if (m.index > last) {
            parts.push({ kind: 'text', label: text.slice(last, m.index), node_id: null, raw: text.slice(last, m.index) })
        }
        parts.push({ kind: 'node', label: m[1], node_id: m[2], raw: m[0] })
        last = m.index + m[0].length
    }
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
export function serializeMaterial(parts) {
    return parts.map(p => {
        if (p.kind === 'node') return `@[${p.label}](node:${p.node_id})`
        return p.label ?? p.raw ?? ''
    }).join('')
}

/**
 * Extrahiert Kanten-Ziel-UUIDs aus einem Material-Text.
 * @param {string} text
 * @returns {string[]}
 */
export function extractNodeTargets(text) {
    if (!text) return []
    return [...text.matchAll(/@\[[^\]]*\]\(node:([0-9a-f-]{36})\)/g)].map(m => m[1])
}
