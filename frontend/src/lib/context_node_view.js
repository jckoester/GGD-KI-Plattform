/**
 * Einheitliche Sicht auf einen Kontextknoten.
 *
 * Dieselben Knoten erreichen die Oberfläche über drei Wege und in drei Formen:
 * die Knotensuche (`/context/nodes`, Feld `id`, Metadaten im Unterobjekt), die
 * Vorschlagssuche (`/context/search`, Feld `node_id`, flache Felder) und die an
 * eine Konversation angehefteten Knoten (`node_id`, flache Felder). Wer sie
 * anzeigen will, sollte nicht an jeder Stelle raten müssen — deshalb hier eine
 * Form, aus der alle drei Anzeigen schöpfen.
 */

import { CONTENT_TYPE_LABELS } from './taxonomy.js'

/**
 * Bringt einen Kontextknoten beliebiger Herkunft auf eine gemeinsame Form.
 *
 * @param {object} node
 * @returns {{id: string|null, title: string, category: string|null,
 *            contentType: string|null, subjectId: number|null,
 *            bpVersion: string|null, nr: string|null}}
 */
export function kontextknotenAnsicht(node) {
    const md = node?.metadata ?? node?.metadata_ ?? {}
    return {
        id: node?.id ?? node?.node_id ?? null,
        title: node?.title ?? '',
        category: node?.category ?? null,
        contentType: node?.content_type ?? null,
        subjectId: node?.subject_id ?? null,
        bpVersion: node?.bp_version ?? md.bp_version ?? null,
        nr: node?.nr ?? md.kompetenz_nr ?? md.nr ?? md.pk_id ?? null,
    }
}

/**
 * Was einen Knoten in einer Liste einordnet — das Fach, sonst der Knotentyp.
 *
 * Bei Bildungsplan-Kompetenzen ist das Fach die fehlende Hälfte: Dass `3.1.1(1)`
 * eine inhaltsbezogene Kompetenz ist, sagt die Nummer bereits; aus welchem Fach
 * sie stammt, sagt nichts — `2.1.1` gibt es in 24 Fächern. Knoten ohne Fach
 * (Dokumente, Nutzerwissen) behalten den Typ, dort ist er die einzige Einordnung.
 *
 * Der Typ geht nicht verloren, wo das Fach ihn verdrängt: Er steht dann im
 * `tooltip`.
 *
 * @param {object} ansicht Ergebnis von {@link kontextknotenAnsicht}
 * @param {Record<number, {name: string}>} subjectMap `subject.id` → Fach
 * @returns {{label: string, tooltip: string}|null}
 */
export function einordnung(ansicht, subjectMap = {}) {
    const fach =
        ansicht?.subjectId != null ? subjectMap?.[ansicht.subjectId]?.name : null
    const typ = ansicht?.contentType
        ? (CONTENT_TYPE_LABELS[ansicht.contentType] ?? ansicht.contentType)
        : null

    if (fach) return { label: fach, tooltip: typ ? `${fach} — ${typ}` : fach }
    return typ ? { label: typ, tooltip: typ } : null
}
