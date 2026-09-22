/**
 * Wie das Ergebnis eines Stundenplan-Abgleichs zu lesen ist.
 *
 * Der Abgleich ändert **Kategorien vorhandener Stunden** — Entfall, Vertretung — und legt
 * seit dem 22.09.2026 **fehlende Termine an**: Wird eine Stunde auf einen Tag verlegt, an
 * dem die Gruppe sonst keinen Unterricht hat, entsteht dort einer. Vorher wurde nur der
 * Entfall am Ursprung geschrieben, und die Planung verlor die Stunde.
 *
 * ⚠️ **Eine Ausnahme bleibt:** Hat die Gruppe **gar keine** Planung, wird nichts angelegt.
 * Dann fehlt nicht ein Termin, sondern das Wochenmuster — und `fehlendesRaster` unten
 * führt zur Einrichtung statt zu einem halben Jahr aus dem Stundenplan.
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
    // Seit der Abgleich Termine anlegt: Wurde einer angelegt, hat die Gruppe eine
    // Planung — dann ist es nicht der Einrichtungsfall.
    if (ergebnis.angelegte?.length) return null
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


/** Wohin eine erkannte Lerngruppe zugeordnet wurde. */
export const ZUR_GRUPPE = "diese"
export const ZU_ANDERER = "andere"
export const OHNE_GRUPPE = "ohne"

/**
 * Was der Stundenplan hergab — lesbar aufbereitet.
 *
 * `GET /calendar/week-patterns` meldet weit mehr, als die Übernahme braucht: die
 * erkannten Lerngruppen samt Fach und Klassen, die Gruppen, die es auf der Plattform noch
 * nicht gibt, unbekannte Fachkürzel und freie Hinweise — darunter seit dem 15.09.2026
 * auch, welche Zuordnung mehrdeutig blieb.
 *
 * Der Editor hat davon nur die eigenen Musterzeilen benutzt und im Fehlschlag „nichts
 * gefunden" gemeldet, mit zwei geratenen Ursachen. Das ist die unangenehmste Auskunft
 * überhaupt: Sie nennt das Ergebnis und verschweigt den Grund, obwohl er vorliegt.
 *
 * Eine Zeile je **Lerngruppe**, nicht je Termin — die Antwort führt jeden Termin einzeln.
 */
export function diagnose(antwort, groupId) {
    // Eine `Map`, denn sie **ist** die Zusammenfassung — der Schlüssel ist die
    // Lerngruppe. Der frühe Ausstieg spart nur das wiederholte Überschreiben.
    const lerngruppen = new Map()
    for (const p of antwort?.patterns ?? []) {
        if (lerngruppen.has(p.gruppe)) continue
        lerngruppen.set(p.gruppe, {
            label: p.gruppe,
            fach: p.subject_slug ?? p.fach ?? null,
            klassen: p.klassen ?? [],
            status: !p.group_id
                ? OHNE_GRUPPE
                : p.group_id === groupId
                  ? ZUR_GRUPPE
                  : ZU_ANDERER,
        })
    }
    return {
        kuerzel: antwort?.kuerzel ?? null,
        wochen: antwort?.wochen?.length ?? 0,
        lerngruppen: [...lerngruppen.values()],
        fehlend: (antwort?.fehlende_gruppen ?? []).map((g) => ({
            name: g.name,
            klassen: g.klassen ?? [],
        })),
        unbekannt: antwort?.unbekannte_faecher ?? [],
        hinweise: antwort?.hinweise ?? [],
    }
}

/** Ob die Diagnose überhaupt etwas zu sagen hat. */
export function diagnoseHatInhalt(d) {
    return Boolean(
        d &&
            (d.lerngruppen.length ||
                d.fehlend.length ||
                d.unbekannt.length ||
                d.hinweise.length),
    )
}

/**
 * Die Zusammenfassung eines Laufs in einem Satz.
 *
 * `geaendert` zählt seit dem 22.09.2026 geänderte **und angelegte** Stunden — die Zahl
 * allein sagt also nicht mehr, was geschah. Deshalb werden angelegte Termine eigens
 * genannt: Eine neue Stunde in der Jahresplanung ist etwas anderes als eine umgestellte.
 */
export function abgleichZusammenfassung(ergebnis) {
    const teile = []
    const angelegt = ergebnis?.angelegte?.length ?? 0
    const geaendert = (ergebnis?.geaendert ?? 0) - angelegt
    teile.push(geaendert === 1 ? "1 Stunde geändert" : `${geaendert} Stunden geändert`)
    if (angelegt) teile.push(angelegt === 1 ? "1 Stunde angelegt" : `${angelegt} Stunden angelegt`)
    if (ergebnis?.verlegungen?.length) teile.push(`${ergebnis.verlegungen.length} Verlegung(en)`)
    if (ergebnis?.konflikte?.length) teile.push(`${ergebnis.konflikte.length} Hinweis(e)`)
    return teile.join(" · ")
}
