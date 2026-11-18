/**
 * Vorige und nächste Stunde nach Terminen der Gruppe im Stundenentwurf (0.48, Päckchen N, F4–F6).
 *
 * Das Backend liefert `lesson.termine = { vorher, nachher }` (Regel in
 * `backend/app/planning/termin_nav.py`). Hier steht, wie die Knöpfe heißen und wann der
 * Einheiten-Knopf daneben überflüssig ist.
 */

const WOCHENTAG = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa']

/** „Do 13.11.“ — kurz genug für einen Knopf. */
export function terminKurz(t) {
    if (!t?.datum) return ''
    const [j, m, d] = String(t.datum).slice(0, 10).split('-').map(Number)
    const tag = WOCHENTAG[new Date(j, m - 1, d).getDay()]
    return `${tag} ${String(d).padStart(2, '0')}.${String(m).padStart(2, '0')}.`
}

/** Tooltip: Termin, Thema und ob es schon einen Entwurf gibt. */
export function terminTitel(t, richtung) {
    if (!t) return ''
    const teile = [`${richtung === 'vorher' ? 'Voriger' : 'Nächster'} Termin: ${terminKurz(t)}`]
    if (t.start_period) teile[0] += `, ${t.start_period}. Stunde`
    if (t.kategorie === 'pruefung') teile.push('Prüfung')
    else if (t.kategorie === 'puffer') teile.push('Puffer')
    if (t.thema) teile.push(t.thema)
    if (!t.stunde_node_id) teile.push('noch kein Entwurf — Klick legt ihn an')
    return teile.join(' · ')
}

/**
 * Den Einheiten-Knopf zeigen? Nicht, wenn er auf dieselbe Stunde führt wie der Termin-Knopf
 * daneben (F6 a: beide bleiben, aber doppelt sagt nichts).
 */
export function einheitKnopfZeigen(einheitZiel, termin) {
    return Boolean(einheitZiel) && einheitZiel !== termin?.stunde_node_id
}
