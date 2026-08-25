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

/** `2016.V2` → `V2`, `2016.V3` → `V3`, `2016` → `Basis`. */
export function fassungsLabel(bpVersion) {
    if (!bpVersion) return null
    const marke = /\.(V\d+(?:\.\d+)?)$/.exec(bpVersion)
    return marke ? marke[1] : 'Basis'
}

/** Die Kompetenznummer eines Knotens — aus den Metadaten, nicht aus dem Titel geraten. */
function nummer(node) {
    const md = node?.metadata ?? node?.metadata_ ?? {}
    return md.kompetenz_nr || md.nr || md.pk_id || null
}

function fassung(node) {
    const md = node?.metadata ?? node?.metadata_ ?? {}
    return md.bp_version || null
}

/**
 * Ermittelt, welche Knoten der Liste einen Fassungshinweis brauchen.
 *
 * Mehrdeutig ist ein Knoten, wenn ein **anderer** Knoten derselben Liste dieselbe Nummer
 * trägt, aber eine andere Fassung. Fach und Nummer allein genügen als Schlüssel: Zwei
 * Fächer mit gleicher Nummer stehen ohnehin nebeneinander, ohne einander zu erklären —
 * das ist kein Fassungsproblem und wird hier nicht behandelt.
 *
 * @param {Array<object>} nodes
 * @returns {Map<string, string>} node.id → Fassungs-Label (nur für mehrdeutige)
 */
export function mehrdeutigeFassungen(nodes) {
    const nachSchluessel = new Map()
    for (const node of nodes ?? []) {
        const nr = nummer(node)
        const bpv = fassung(node)
        if (!nr || !bpv) continue
        const schluessel = `${node.subject_id ?? ''}|${nr}`
        if (!nachSchluessel.has(schluessel)) nachSchluessel.set(schluessel, [])
        nachSchluessel.get(schluessel).push({ id: node.id, bpv })
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
