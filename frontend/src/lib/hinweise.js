/**
 * Parser und Serializer für die Hinweise-Token-Notation.
 *
 * Token-Notation (round-trip-stabil):
 *   Leitperspektive        : @[<Label>](lp:<uuid>)
 *   Leitperspektive-Aspekt : @[<Label>](lpa:<uuid>)
 *   Leitlinie der Schule   : @[<Label>](lb:<uuid>)    (0.50)
 *   Aspekt einer Leitlinie : @[<Label>](lba:<uuid>)   (0.50)
 *   Cross-Fach-IK          : #[<Label>](ik:<uuid>)
 *   Alles andere           : unveränderter Freitext
 */

// lpa muss vor lp stehen (lba vor lb), damit der längere Prefix zuerst matcht
const ANY_TOKEN = /(@\[[^\]]*\]\(lpa:[0-9a-f-]{36}\)|@\[[^\]]*\]\(lp:[0-9a-f-]{36}\)|@\[[^\]]*\]\(lba:[0-9a-f-]{36}\)|@\[[^\]]*\]\(lb:[0-9a-f-]{36}\)|#\[[^\]]*\]\(ik:[0-9a-f-]{36}\))/g

/** Token-Arten mit `@`, in der Reihenfolge des Musters oben. */
const AT_ARTEN = ['lpa', 'lp', 'lba', 'lb']

/**
 * Zerlegt einen Hinweise-Text in Parts.
 * @param {string} text
 * @returns {Array<{kind:'text'|'lp'|'lpa'|'lb'|'lba'|'ik', label:string, node_id:string|null, raw:string}>}
 */
export function parseHinweise(text) {
    if (!text) return []

    const parts = []
    let last = 0

    for (const m of text.matchAll(ANY_TOKEN)) {
        if (m.index > last) {
            parts.push({ kind: 'text', label: text.slice(last, m.index), node_id: null, raw: text.slice(last, m.index) })
        }

        const token = m[0]
        const atMatch  = token.match(/^@\[([^\]]*)\]\((lpa|lp|lba|lb):([0-9a-f-]{36})\)$/)
        const ikMatch  = token.match(/^#\[([^\]]*)\]\(ik:([0-9a-f-]{36})\)$/)

        if (atMatch && AT_ARTEN.includes(atMatch[2])) {
            parts.push({ kind: atMatch[2], label: atMatch[1], node_id: atMatch[3], raw: token })
        } else if (ikMatch) {
            parts.push({ kind: 'ik', label: ikMatch[1], node_id: ikMatch[2], raw: token })
        }

        last = m.index + token.length
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
export function serializeHinweise(parts) {
    return parts.map(p => {
        if (AT_ARTEN.includes(p.kind)) return `@[${p.label}](${p.kind}:${p.node_id})`
        if (p.kind === 'ik')  return `#[${p.label}](ik:${p.node_id})`
        return p.label ?? p.raw ?? ''
    }).join('')
}

// Fach-Codes stammen aus `config/subjects.yaml` und sind kürzer und bunter als das
// naheliegende Muster „zwei bis sechs Großbuchstaben": Es gibt einbuchstabige (D, G, M)
// und solche mit Ziffer (E1, F2, L2, SPA3). Jenes Muster schloss 8 von 27 Fächern von
// der Autovervollständigung aus — darunter Deutsch, Mathematik, Geschichte und sämtliche
// Fremdsprachen.
//
// Gültig ist deshalb: ein Großbuchstabe, dann bis zu sieben weitere Großbuchstaben oder
// Ziffern. Bewusst großzügig — ob es den Code wirklich gibt, entscheidet ohnehin erst der
// Server (`/context/subjects/by-code/…`; 404 → kein Dropdown).
const IK_TRIGGER = /#([A-ZÄÖÜ][A-ZÄÖÜ0-9]{0,7})(?:\s+(\S*))?$/
const LP_TRIGGER = /@([^\s@#]*)$/

/**
 * Erkennt den aktiven Autocomplete-Trigger links vom Cursor.
 *
 *   `@<query>`           → Leitperspektiven und Leitlinien der Schule
 *   `#<FACH> [<nr>]`     → Cross-Fach-IK-Suche im Zielfach
 *
 * @param {string} text
 * @param {number} cursorPos
 * @returns {{kind:'lp'|'ik', query:string, matchStart:number, fachCode?:string}|null}
 */
export function getActiveTrigger(text, cursorPos) {
    const before = text.slice(0, cursorPos)

    const lpMatch = before.match(LP_TRIGGER)
    if (lpMatch) {
        return {
            kind: 'lp',
            query: lpMatch[1],
            matchStart: before.length - lpMatch[0].length,
        }
    }

    const ikMatch = before.match(IK_TRIGGER)
    if (ikMatch) {
        return {
            kind: 'ik',
            fachCode: ikMatch[1],
            query: ikMatch[2] ?? '',
            matchStart: before.length - ikMatch[0].length,
        }
    }

    return null
}

/**
 * Extrahiert Kanten-Ziel-UUIDs aus einem Hinweise-Text.
 * @param {string} text
 * @returns {{ lp: string[], lpa: string[], lb: string[], lba: string[], ik: string[] }}
 */
export function extractEdgeTargets(text) {
    if (!text) return { lp: [], lpa: [], lb: [], lba: [], ik: [] }
    const lpa = [...text.matchAll(/@\[[^\]]*\]\(lpa:([0-9a-f-]{36})\)/g)].map(m => m[1])
    const lp  = [...text.matchAll(/@\[[^\]]*\]\(lp:([0-9a-f-]{36})\)/g)].map(m => m[1])
    const lba = [...text.matchAll(/@\[[^\]]*\]\(lba:([0-9a-f-]{36})\)/g)].map(m => m[1])
    const lb  = [...text.matchAll(/@\[[^\]]*\]\(lb:([0-9a-f-]{36})\)/g)].map(m => m[1])
    const ik  = [...text.matchAll(/#\[[^\]]*\]\(ik:([0-9a-f-]{36})\)/g)].map(m => m[1])
    return { lp, lpa, lb, lba, ik }
}

/**
 * Natürliche Ordnung von Kürzeln: „SDG2“ vor „SDG13“.
 * @param {string} a
 * @param {string} b
 */
export function kuerzelVergleich(a, b) {
    return String(a ?? '').localeCompare(String(b ?? ''), 'de', { numeric: true })
}

/**
 * Die Auswahl nach `@` für die Leitlinien der Schule (0.50): je Leitlinie ein Kopf, darunter
 * ihre Aspekte. Zugeordnet wird über Kürzel (`metadata.leitlinie` am Aspekt). Ein Treffer im
 * Kopf zeigt alle Aspekte; sonst nur die passenden.
 *
 * @param {Array<{id:string, title:string, content_type:string, metadata?:object}>} nodes
 * @param {string} query
 */
export function leitlinienAuswahl(nodes, query) {
    const q = (query ?? '').toLowerCase()
    const k = (n, feld) => String(n.metadata?.[feld] ?? '').replace(/\s+/g, '').toUpperCase()
    const leitlinien = nodes
        .filter((n) => n.content_type === 'leitbild')
        .sort((a, b) => kuerzelVergleich(k(a, 'kuerzel'), k(b, 'kuerzel')))
    const items = []
    for (const lb of leitlinien) {
        const kuerzel = k(lb, 'kuerzel')
        const aspekte = nodes
            .filter((n) => n.content_type === 'leitbild_aspekt' && k(n, 'leitlinie') === kuerzel)
            .sort((a, b) => kuerzelVergleich(k(a, 'kuerzel'), k(b, 'kuerzel')))
        const kopfTrifft = !q || lb.title.toLowerCase().includes(q) || kuerzel.toLowerCase().includes(q)
        const passend = kopfTrifft ? aspekte : aspekte.filter(
            (a) => a.title.toLowerCase().includes(q) || k(a, 'kuerzel').toLowerCase().includes(q))
        if (!kopfTrifft && passend.length === 0) continue
        items.push({
            node_id: lb.id, label: lb.title, sublabel: kuerzel || null, kind: 'lb', isHead: true,
            serialized: `@[${lb.title}](lb:${lb.id})`,
        })
        for (const a of passend) {
            const label = `${k(a, 'kuerzel')}: ${a.title}`
            items.push({
                node_id: a.id, label, sublabel: null, kind: 'lba', indented: true,
                serialized: `@[${label}](lba:${a.id})`,
            })
        }
    }
    return items
}
