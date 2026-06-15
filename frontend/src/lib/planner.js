// Utilities für die Unterrichtsplanungs-UI

export const UE_PALETTE = [
    ['#4a7fb5', '#7aabdf'],
    ['#5ba37a', '#85c9a0'],
    ['#b07fb8', '#d4a8da'],
    ['#c9504a', '#e88080'],
    ['#c9a227', '#e8c55f'],
    ['#4a97b5', '#7ac5df'],
    ['#a87f5b', '#d4a880'],
    ['#7f9ab5', '#a8c5da'],
]

/** Gibt die Farbe einer UE zurück (Light- oder Dark-Variante). */
export function ueColor(unit, dark = false) {
    const farbe = unit?.metadata_?.farbe ?? 0
    const pair = UE_PALETTE[farbe % UE_PALETTE.length]
    return dark ? pair[1] : pair[0]
}

/**
 * ISO-Wochennummer und zugehöriges Jahr für einen Datum-String (YYYY-MM-DD).
 *
 * Bewusst durchgängig UTC: Würde man mit lokalen Date-Objekten rechnen, verschiebt
 * der Sommerzeit-Übergang (ein 23-Stunden-Tag Ende März) die Millisekunden-Differenz
 * unter eine 7-Tage-Grenze und liefert über die Umstellung hinweg falsche Wochen.
 */
export function isoWeek(dateStr) {
    const d = new Date(dateStr + 'T00:00:00Z')
    const dow = (d.getUTCDay() + 6) % 7 // Mon=0 … Sun=6
    d.setUTCDate(d.getUTCDate() - dow + 3) // auf den Donnerstag derselben ISO-Woche
    const thursday = d.getTime()
    const year = d.getUTCFullYear()
    const jan1Dow = (new Date(Date.UTC(year, 0, 1)).getUTCDay() + 6) % 7
    const firstThursday = Date.UTC(year, 0, 1 + ((3 - jan1Dow + 7) % 7))
    const week = 1 + Math.round((thursday - firstThursday) / 604800000)
    return { week, year }
}

/** Wochentag-Index (Mo=0 … So=6), UTC-basiert. */
export function weekdayIndex(dateStr) {
    return (new Date(dateStr + 'T00:00:00Z').getUTCDay() + 6) % 7
}

/** "KW 42" */
export function kwLabel(dateStr) {
    const { week } = isoWeek(dateStr)
    return `KW ${week}`
}

/** "Mo", "Di", … */
export function weekdayLabel(dateStr) {
    const d = new Date(dateStr + 'T00:00:00')
    const idx = (d.getDay() + 6) % 7
    return ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][idx]
}

/** "22.9." */
export function dateLabel(dateStr) {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('de-DE', { day: 'numeric', month: 'numeric' })
}

/** "3. Std" oder "5.–6. Std" */
export function periodLabel(slot) {
    if (!slot.start_period) return ''
    if (slot.periods >= 2) return `${slot.start_period}.–${slot.start_period + 1}. Std`
    return `${slot.start_period}. Std`
}

export const PRIO_COLORS = {
    kern:       ['#4a7fb5', '#7aabdf'],
    uebung:     ['#5ba37a', '#85c9a0'],
    vertiefung: ['#b07fb8', '#d4a8da'],
}

export const PRIO_LABELS = {
    kern: 'Kern',
    uebung: 'Übung',
    vertiefung: 'Vertiefung',
}

export const KATEGORIE_LABELS = {
    unterricht: 'Unterricht',
    pruefung: 'Prüfung',
    puffer: 'Puffer',
    ausfall: 'Ausfall',
    vertretung: 'Vertretung',
}

/**
 * Gruppiert Slots nach Kalenderwochen und fügt Ferien- und Halbjahresbänder ein.
 *
 * Feiertage und unterrichtsfreie Tage werden als Sondertag-Zeilen eingefügt —
 * aber nur an Wochentagen, an denen die Gruppe tatsächlich unterrichtet (aus den
 * Slots abgeleitet, je Halbjahr). So ersetzt der Sondertag genau die Stunde, die
 * an diesem Tag ausfiele: Fällt ein Slot auf einen Sondertag (z. B. weil das
 * Raster vor der Pflege der school_year.yaml erzeugt wurde), wird der Slot
 * unterdrückt und die Sondertag-Zeile **an seiner Stelle** gezeigt — nie beides.
 * Liegt der einzige Unterrichtstag einer Woche auf dem Sondertag, erscheint die
 * Woche trotzdem (mit nur der Sondertag-Zeile).
 *
 * Jede Woche erhält eine `rows`-Liste aus gemischten Einträgen:
 * `{ kind: 'slot', slot, date }` und `{ kind: 'special', art, name, date }`,
 * chronologisch sortiert.
 *
 * @param {Array} slots - LessonSlot-Objekte aus dem Overview-Endpoint
 * @param {{ ferien?: Array, feiertage?: Array, unterrichtsfreie?: Array, halbjahreswechsel?: string, beginn?: string, ende?: string }} calendar
 * @returns Array of items:
 *   { type: 'week', key, week, year, slots, rows }
 *   { type: 'ferien', name, von, bis }
 *   { type: 'halbjahr' }
 */
export function groupSlotsByWeek(
    slots,
    { ferien = [], feiertage = [], unterrichtsfreie = [], halbjahreswechsel, beginn, ende } = {},
) {
    if (!slots?.length) return []

    const sorted = [...slots].sort((a, b) => a.date.localeCompare(b.date))
    // Sondertage werden am Schuljahr begrenzt (nicht am Slot-Bereich): Fällt der
    // letzte Unterrichtstag des Jahres auf einen unterrichtsfreien Tag, läge er
    // hinter dem letzten Slot und würde sonst verschwinden — der Plan endete
    // kommentarlos vorzeitig. Fallback auf den Slot-Bereich, falls nicht gesetzt.
    const rangeStart = beginn ?? sorted[0].date
    const rangeEnd = ende ?? sorted.at(-1).date

    // Unterrichtswochentage der Gruppe je Halbjahr (Mo=0 … So=6) aus den Slots ableiten.
    const teachWd = new Map() // halbjahr → Set<weekday>
    for (const slot of sorted) {
        if (!teachWd.has(slot.halbjahr)) teachWd.set(slot.halbjahr, new Set())
        teachWd.get(slot.halbjahr).add(weekdayIndex(slot.date))
    }

    const hjOf = (dateStr) =>
        halbjahreswechsel && dateStr >= halbjahreswechsel ? 2 : 1
    const inFerien = (dateStr) =>
        ferien.some((f) => f.von <= dateStr && dateStr <= f.bis)

    // Relevante Sondertage bestimmen: im Planungszeitraum, kein Ferientag und an
    // einem Unterrichtswochentag der Gruppe (im jeweiligen Halbjahr).
    const specialByDate = new Map() // datum → { art, name }
    for (const t of [
        ...feiertage.map((t) => ({ ...t, art: 'feiertag' })),
        ...unterrichtsfreie.map((t) => ({ ...t, art: 'unterrichtsfrei' })),
    ]) {
        if (!t.datum || t.datum < rangeStart || t.datum > rangeEnd) continue
        if (inFerien(t.datum)) continue
        if (!teachWd.get(hjOf(t.datum))?.has(weekdayIndex(t.datum))) continue
        if (!specialByDate.has(t.datum)) {
            specialByDate.set(t.datum, { art: t.art, name: t.name ?? null })
        }
    }

    const byWeek = new Map()
    const ensureWeek = (dateStr) => {
        const { week, year } = isoWeek(dateStr)
        const key = `${year}-W${String(week).padStart(2, '0')}`
        if (!byWeek.has(key)) byWeek.set(key, { key, week, year, slots: [], special: [] })
        return byWeek.get(key)
    }

    // Slots einsortieren — außer wenn ihr Datum ein Sondertag ist (dann ersetzt
    // ihn die Sondertag-Zeile; ein solcher Slot ist veralteter Rasterstand).
    for (const slot of sorted) {
        if (specialByDate.has(slot.date)) continue
        ensureWeek(slot.date).slots.push(slot)
    }
    // Sondertage einsortieren (legt bei Bedarf eine ansonsten leere Woche an).
    for (const [datum, info] of specialByDate) {
        ensureWeek(datum).special.push({
            kind: 'special',
            art: info.art,
            name: info.name,
            date: datum,
        })
    }

    // Repräsentatives Erst-/Letztdatum einer Woche (Slots + Sondertage gemischt).
    const weekDates = (w) => [
        ...w.slots.map((s) => s.date),
        ...w.special.map((s) => s.date),
    ]
    const repFirst = (w) => weekDates(w).reduce((a, b) => (b < a ? b : a))
    const repLast = (w) => weekDates(w).reduce((a, b) => (b > a ? b : a))
    const weekHj = (w) => (w.slots.length ? w.slots[0].halbjahr : hjOf(repFirst(w)))

    const weekKeys = [...byWeek.keys()].sort()
    const items = []
    let halbjahrInserted = false

    for (let i = 0; i < weekKeys.length; i++) {
        const weekData = byWeek.get(weekKeys[i])

        if (i > 0) {
            const prevData = byWeek.get(weekKeys[i - 1])
            const gapStart = new Date(repLast(prevData) + 'T00:00:00')
            gapStart.setDate(gapStart.getDate() + 1)
            const gapEnd = new Date(repFirst(weekData) + 'T00:00:00')
            gapEnd.setDate(gapEnd.getDate() - 1)

            // Ferien-Bänder im Gap
            if (gapStart <= gapEnd) {
                for (const f of ferien) {
                    const fStart = new Date(f.von + 'T00:00:00')
                    const fEnd = new Date(f.bis + 'T00:00:00')
                    if (fStart <= gapEnd && fEnd >= gapStart) {
                        items.push({ type: 'ferien', name: f.name, von: f.von, bis: f.bis })
                    }
                }
            }

            // Halbjahresbruch zwischen HJ1-Ende und HJ2-Beginn
            if (!halbjahrInserted && weekHj(prevData) === 1 && weekHj(weekData) === 2) {
                items.push({ type: 'halbjahr' })
                halbjahrInserted = true
            }
        }

        const rows = [
            ...weekData.slots.map((s) => ({ kind: 'slot', slot: s, date: s.date })),
            ...weekData.special,
        ].sort((a, b) => a.date.localeCompare(b.date))

        items.push({
            type: 'week',
            key: weekData.key,
            week: weekData.week,
            year: weekData.year,
            slots: weekData.slots,
            rows,
        })
    }

    return items
}
