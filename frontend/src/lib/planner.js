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

/** ISO-Wochennummer und zugehöriges Jahr für einen Datum-String (YYYY-MM-DD). */
export function isoWeek(dateStr) {
    const d = new Date(dateStr + 'T00:00:00')
    const dow = (d.getDay() + 6) % 7 // Mon=0 … Sun=6
    const thursday = new Date(d)
    thursday.setDate(d.getDate() - dow + 3)
    const year = thursday.getFullYear()
    const jan1 = new Date(year, 0, 1)
    const jan1Dow = (jan1.getDay() + 6) % 7
    const firstThursday = new Date(year, 0, 1 + ((3 - jan1Dow + 7) % 7))
    const week = 1 + Math.floor((thursday - firstThursday) / 604800000)
    return { week, year }
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
 * @param {Array} slots - LessonSlot-Objekte aus dem Overview-Endpoint
 * @param {{ ferien?: Array, halbjahreswechsel?: string }} calendar
 * @returns Array of items:
 *   { type: 'week', key, week, year, slots }
 *   { type: 'ferien', name, von, bis }
 *   { type: 'halbjahr' }
 */
export function groupSlotsByWeek(slots, { ferien = [], halbjahreswechsel } = {}) {
    if (!slots?.length) return []

    const sorted = [...slots].sort((a, b) => a.date.localeCompare(b.date))

    const byWeek = new Map()
    for (const slot of sorted) {
        const { week, year } = isoWeek(slot.date)
        const key = `${year}-W${String(week).padStart(2, '0')}`
        if (!byWeek.has(key)) byWeek.set(key, { key, week, year, slots: [] })
        byWeek.get(key).slots.push(slot)
    }

    const weekKeys = [...byWeek.keys()].sort()
    const items = []
    let halbjahrInserted = false

    for (let i = 0; i < weekKeys.length; i++) {
        const weekData = byWeek.get(weekKeys[i])

        if (i > 0) {
            const prevData = byWeek.get(weekKeys[i - 1])
            const prevLastDate = prevData.slots.at(-1).date
            const currFirstDate = weekData.slots[0].date

            const gapStart = new Date(prevLastDate + 'T00:00:00')
            gapStart.setDate(gapStart.getDate() + 1)
            const gapEnd = new Date(currFirstDate + 'T00:00:00')
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
            if (!halbjahrInserted) {
                const prevHj = prevData.slots[0]?.halbjahr
                const currHj = weekData.slots[0]?.halbjahr
                if (prevHj === 1 && currHj === 2) {
                    items.push({ type: 'halbjahr' })
                    halbjahrInserted = true
                }
            }
        }

        items.push({ type: 'week', ...weekData })
    }

    return items
}
