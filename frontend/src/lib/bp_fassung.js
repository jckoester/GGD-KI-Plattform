/**
 * Bildungsplan-Fassung in Auswahllisten kenntlich machen.
 *
 * Während eines Editionswechsels sind mehrere Fassungen gleichzeitig aktiv — das ist der
 * Normalfall, nicht die Ausnahme. In Listen, die **ohne** Jahrgangsbezug suchen (Chat,
 * generische Knotensuche), stehen dann zwei Kompetenzen mit **gleicher Nummer und
 * verschiedenem Text** kommentarlos nebeneinander. Wer sie einordnen kann — Lehrkräfte —
 * kann das nur, wenn die Fassung dabeisteht.
 *
 * **Nur wo es nötig ist.** Ein Hinweis an jedem Treffer wäre Rauschen: Der Bildungsplan
 * hat für die allermeisten Nummern nur eine Fassung. Markiert wird deshalb ausschließlich,
 * was in der *angezeigten Liste* mehrdeutig ist.
 *
 * Die editionsgefilterten Auswahlfelder (IK-/PK-Selektor, Fachplan-Ansicht) brauchen das
 * nicht — dort steht die Fassung ohnehin fest.
 */

import { kontextknotenAnsicht } from './context_node_view.js'

/** `2016.V2` → `V2`, `2016.V3` → `V3`, `2016` → `Basis`. */
export function fassungsLabel(bpVersion) {
    if (!bpVersion) return null
    const marke = /\.(V\d+(?:\.\d+)?)$/.exec(bpVersion)
    return marke ? marke[1] : 'Basis'
}

/**
 * Was zwei Knoten zu Fassungen **desselben** Gegenstands macht.
 *
 * Die Nummer, wo es eine gibt — sie ist je Fach eindeutig. Wo es keine gibt, der Titel:
 * **Operatoren tragen keine Kompetenznummer**, und genau sie stehen mehrfach im selben
 * Fach. „nennen" gibt es in Englisch in drei Editionen, in vier weiteren Fächern in
 * zweien. Vor 09/2026 verlangte diese Funktion eine Nummer und übersprang die Operatoren
 * deshalb — in einer Trefferliste standen dann drei identische Zeilen „Englisch ·
 * nennen" ohne jedes Unterscheidungsmerkmal.
 *
 * Das Fach gehört in den Schlüssel: Zwei Fächer mit gleicher Nummer stehen ohnehin
 * nebeneinander, ohne einander zu erklären — das ist kein Fassungsproblem.
 */
function fassungsSchluessel({ nr, subjectId, title }) {
    const kern = nr || (title || '').trim().toLowerCase()
    return kern ? `${subjectId ?? ''}|${kern}` : null
}

/**
 * Ermittelt, welche Knoten der Liste einen Fassungshinweis brauchen.
 *
 * Mehrdeutig ist ein Knoten, wenn ein **anderer** Knoten derselben Liste denselben
 * Gegenstand meint (siehe `fassungsSchluessel`), aber eine andere Fassung trägt.
 *
 * Nimmt Knoten aus allen drei Quellen (siehe `context_node_view.js`); der Schlüssel der
 * Rückgabe ist die ID, die der übergebene Knoten selbst trägt (`id` oder `node_id`).
 *
 * @param {Array<object>} nodes
 * @returns {Map<string, string>} Knoten-ID → Fassungs-Label (nur für mehrdeutige)
 */
export function mehrdeutigeFassungen(nodes) {
    const nachSchluessel = new Map()
    for (const node of nodes ?? []) {
        const ansicht = kontextknotenAnsicht(node)
        const { id, bpVersion: bpv } = ansicht
        // Ohne Fassung ist ein Knoten keine Fassung von irgendetwas.
        if (!bpv) continue
        const schluessel = fassungsSchluessel(ansicht)
        if (!schluessel) continue
        if (!nachSchluessel.has(schluessel)) nachSchluessel.set(schluessel, [])
        nachSchluessel.get(schluessel).push({ id, bpv })
    }

    const markiert = new Map()
    for (const eintraege of nachSchluessel.values()) {
        const fassungen = new Set(eintraege.map((e) => e.bpv))
        if (fassungen.size < 2) continue
        for (const e of eintraege) {
            const label = fassungsLabel(e.bpv)
            if (label) markiert.set(e.id, label)
        }
    }
    return markiert
}
