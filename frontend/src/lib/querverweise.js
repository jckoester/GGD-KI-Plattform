/**
 * Querverweise des Bildungsplans in andere Fächer (Päckchen AY Teil 1, Schritt 4).
 *
 * Die Daten liefert `POST /context/querverweise` (`backend/app/context/querverweise.py`):
 * je Kompetenz eine Liste mit Fach, Kürzel, Icon, Farbe, Nummer, Kurztitel, Stufen, Status.
 * Hier liegt nur, was die Anzeige daraus macht — als reine Funktionen, damit es testbar ist.
 *
 * Entschieden (Jan, 25.11.2026): An der Kompetenz steht das **Fach** (Kürzel und Icon) in
 * **Fachfarbe**, die Einzelheiten klappen auf (F8). Bereiche bleiben Bereiche (F3 a).
 */

/** Kürzel eines Fachs: Bildungsplan-Code, sonst die ersten drei Buchstaben (Deutsch hat keinen Code). */
export function fachKuerzel(eintrag) {
    if (eintrag?.fach_code) return eintrag.fach_code
    const name = (eintrag?.fach || '').trim()
    return name ? name.slice(0, 3) : '?'
}

/** Die Fächer einer Liste, je Fach einmal, in der Reihenfolge der Liste (sie ist schon sortiert). */
export function faecher(liste) {
    const gesehen = new Map()
    for (const e of liste || []) {
        if (!gesehen.has(e.fach_id)) {
            gesehen.set(e.fach_id, {
                fach_id: e.fach_id, fach: e.fach, kuerzel: fachKuerzel(e),
                icon: e.icon ?? null, color: e.color ?? null, anzahl: 0,
            })
        }
        gesehen.get(e.fach_id).anzahl += 1
    }
    return [...gesehen.values()]
}

/** „Kl. 7/8“, „Kl. 9“, oder leer, wenn der Bildungsplan keine Stufen nennt. */
export function stufenText(eintrag) {
    const { min_grade: von, max_grade: bis } = eintrag || {}
    if (von == null && bis == null) return ''
    if (von == null || bis == null || von === bis) return `Kl. ${von ?? bis}`
    return `Kl. ${von}/${bis}`
}

/** Hinweis für eine Fassung, die erst später gilt: „ab 2027/28“ oder „künftige Fassung“. */
export function kuenftigText(eintrag) {
    if (eintrag?.status !== 'upcoming') return ''
    const jahr = eintrag.ab_schuljahr
    if (!jahr) return 'künftige Fassung'
    return `ab ${jahr}/${String((jahr + 1) % 100).padStart(2, '0')}`
}

/** Was als Zeile in der aufgeklappten Liste steht (ohne Fach — das steht davor). */
export function zeilenText(eintrag) {
    const teile = []
    const stufen = stufenText(eintrag)
    if (stufen) teile.push(stufen)
    const nr = eintrag?.nr ? `${eintrag.typ === 'bereich' ? 'Bereich ' : ''}${eintrag.nr}` : ''
    teile.push([nr, eintrag?.titel].filter(Boolean).join(' '))
    return teile.join(' · ')
}

/**
 * Fundstelle im anderen Fach (Schritt 5): „PH 7/8 › Kapitel Mechanik“, Entwürfe gekennzeichnet.
 * Kapitel und Curriculum heißen in der Plattform oft ähnlich — beide stehen da, damit man
 * weiß, wo man nachsieht.
 */
export function fundstelleText(f) {
    const ort = [f?.curriculum, f?.kapitel].filter(Boolean).join(' › ')
    return f?.status === 'draft' ? `${ort} (Entwurf)` : ort
}

/** Pfad zur Fundstelle: das Curriculum des anderen Fachs, aufgeklappt beim Kapitel. */
export function fundstellePfad(f) {
    return `/knowledge/curriculum/${f.curriculum_id}#kapitel-${f.kapitel_id}`
}

/** Kurzer Text für Tooltip und Bildschirmleser: „Bezug zu Physik (2), Chemie“. */
export function bezugText(liste) {
    const f = faecher(liste)
    if (!f.length) return ''
    return 'Bezug zu ' + f.map((x) => (x.anzahl > 1 ? `${x.fach} (${x.anzahl})` : x.fach)).join(', ')
}

/** Alle verknüpften Kompetenz-IDs eines Curriculums (IK-Spalte der Einträge). */
export function kompetenzIdsImCurriculum(curriculum) {
    const ids = new Set()
    for (const kap of curriculum?.kapitel || []) {
        for (const ls of kap.lernsequenzen || []) {
            for (const eintrag of ls.metadata?.eintraege || []) {
                if (!Array.isArray(eintrag.ik)) continue
                for (const ik of eintrag.ik) {
                    if (ik && typeof ik === 'object' && ik.node_id) ids.add(ik.node_id)
                }
            }
        }
    }
    return [...ids]
}

/** Alle inhaltsbezogenen Kompetenzen eines Fachplans (Bildungsplan-Ansicht), über die Bereiche rekursiv. */
export function kompetenzIdsImFachplan(plan) {
    const ids = []
    const besuche = (ld) => {
        for (const ik of ld?.ik_kompetenzen || []) if (ik?.id) ids.push(ik.id)
        for (const unter of ld?.unter_leitideen || []) besuche(unter)
    }
    for (const ld of plan?.leitideen || []) besuche(ld)
    return [...new Set(ids)]
}

/** Die IDs, die noch nicht im Zwischenspeicher stehen (Bearbeitung: nur Neues nachladen). */
export function fehlendeIds(ids, speicher) {
    return (ids || []).filter((id) => !speicher.has(id))
}

/**
 * Die Antwort des Servers in den Zwischenspeicher übernehmen. Gefragte IDs ohne Querverweis
 * fehlen in der Antwort — sie bekommen eine leere Liste, damit sie nicht erneut gefragt werden.
 */
export function uebernehmen(speicher, gefragt, antwort) {
    const neu = new Map(speicher)
    for (const id of gefragt) neu.set(id, antwort?.[id] ?? [])
    return neu
}
