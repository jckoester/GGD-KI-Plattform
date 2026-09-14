/**
 * Wie das Ergebnis eines Stundenplan-Abgleichs zu lesen ist.
 *
 * Der Abgleich ändert **Kategorien vorhandener Stunden** — Entfall, Vertretung — und legt
 * keine an. Das ist Absicht und in `app/calendar/sync.py` als Grenze festgehalten: „Ohne
 * passenden Slot wird nichts angelegt."
 */

/** Grund, den das Backend an einen Konflikt schreibt, wenn die Planung die Stunde nicht kennt. */
export const OHNE_SLOT = "kein_slot"

/**
 * Meldung für den Fall „die Jahresplanung ist noch leer" — oder `null`.
 *
 * **Warum das eine eigene Meldung braucht.** Hat eine Gruppe noch keine Stunden, meldet
 * der Abgleich für *jede* Stunde des Stundenplans „kein Slot" und ändert nichts. Die
 * Zusammenfassung „0 Stunden geändert · 48 Hinweis(e)" ist dann zwar richtig, sagt aber
 * das Falsche: Sie klingt nach Fehlschlag, während bloß der Unterbau fehlt — und die 48
 * ist keine Auskunft, sondern die Zahl der Stunden im Stundenplan. Genau daran ist am
 * 13.09.2026 eine Einrichtung hängengeblieben.
 *
 * Streng: **alle** Hinweise müssen diesen Grund haben und es darf nichts geändert worden
 * sein. Sonst gäbe es echte Befunde, die diese Meldung verdecken würde.
 */
export function fehlendesRaster(ergebnis) {
    const konflikte = ergebnis?.konflikte ?? []
    if (!konflikte.length) return null
    if (ergebnis.geaendert !== 0) return null
    if (ergebnis.verlegungen?.length) return null
    if (!konflikte.every((k) => k.grund === OHNE_SLOT)) return null
    return (
        "Für diese Gruppe sind noch keine Stunden angelegt — der Abgleich hat nichts, " +
        "woran er arbeiten könnte. Zuerst im Wochenmuster „Aus Stundenplan übernehmen“, " +
        "speichern und Stunden erzeugen."
    )
}

/**
 * Die flache Musterliste des Vorschlags-Endpunkts nach Gruppen bündeln.
 *
 * `GET /calendar/week-patterns` liefert eine Zeile je erkanntem Termin, jede mit
 * `group_id` — gesetzt nur, wenn es die Gruppe auf der Plattform gibt. Für die
 * Sammelübernahme ist die Gruppe die Einheit: Ein Wochenmuster wird je Gruppe und
 * Halbjahr **als Ganzes** geschrieben (`PUT /planning/groups/{id}/pattern` ersetzt),
 * nicht zeilenweise.
 *
 * Zeilen ohne `group_id` fallen heraus — sie gehören zu Lerngruppen, die es auf der
 * Plattform nicht gibt, und dorthin lässt sich nichts schreiben. Wie viele das sind,
 * steht in `fehlende_gruppen` der Antwort; die Zahl ist für die Oberfläche interessant,
 * für die Übernahme nicht.
 */
export function rasterJeGruppe(antwort) {
    const nachGruppe = new Map()
    for (const p of antwort?.patterns ?? []) {
        if (!p.group_id) continue
        if (!nachGruppe.has(p.group_id)) {
            nachGruppe.set(p.group_id, { group_id: p.group_id, gruppe: p.gruppe, zeilen: [] })
        }
        nachGruppe.get(p.group_id).zeilen.push({
            weekday: p.weekday,
            start_period: p.start_period,
            periods: p.periods,
            rhythmus: p.rhythmus,
            sicher: p.sicher,
        })
    }
    return [...nachGruppe.values()]
        .map((g) => ({ ...g, unsicher: g.zeilen.filter((z) => !z.sicher).length }))
        // Stabile Reihenfolge: Die Map bewahrt zwar die Einfügereihenfolge, aber die
        // hängt daran, in welcher Reihenfolge der Stundenplan die Termine liefert.
        .sort((a, b) => (a.gruppe ?? "").localeCompare(b.gruppe ?? "", "de"))
}
