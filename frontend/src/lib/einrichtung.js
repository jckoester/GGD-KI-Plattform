/**
 * Einrichtung beim ersten Login (0.43, Plan `Onboarding-Lehrkraefte-Plan.md`) — reine Regeln.
 *
 * Welche Seiten eine Rolle durchgeht, welche entfällt, wo ein Wiedereinstieg beginnt und wann
 * der Dialog von selbst aufgeht. Der Stand kommt von `GET /einrichtung`; Seiteninhalte und
 * Speichern stehen in `EinrichtungDialog.svelte`.
 *
 * **Eine Seite dazunehmen** (etwa für Schüler:innen, 0.47): Schlüssel in `SEITEN`, Liste in
 * `SEITEN_JE_ROLLE`, Inhalt im Dialog. Die gespeicherte Seitennummer zählt in der **vollen**
 * Liste der Rolle — eine entfallene Seite verschiebt den Wiedereinstieg nicht.
 */

import { uebertragText, zuwachsText } from './budget_text.js'
import { ausEuro, text as einheitenText } from './einheiten.js'

export const SEITEN = {
    willkommen: { titel: 'Willkommen' },
    gut_zu_wissen: { titel: 'Gut zu wissen' },
    stufe: { titel: 'Umfang der Oberfläche' },
    stundenplan: { titel: 'Stundenplan' },
    gruppen: { titel: 'Unterrichtsgruppen' },
    fertig: { titel: 'Fertig' },
}

export const SEITEN_JE_ROLLE = {
    teacher: ['willkommen', 'gut_zu_wissen', 'stufe', 'stundenplan', 'gruppen', 'fertig'],
}

/** Die Rolle, nach der sich die Einrichtung richtet — `null`: keine Einrichtung (reine Admins, F10). */
export function einrichtungsRolle(rollen) {
    return (rollen ?? []).includes('teacher') ? 'teacher' : null
}

/**
 * Die Seiten, die tatsächlich gezeigt werden. Ohne Stundenplanquelle entfällt „Stundenplan“.
 * @param {string|null} rolle
 * @param {{ stundenplan?: { configured?: boolean } } | null} daten Antwort von `GET /einrichtung`
 */
export function sichtbareSeiten(rolle, daten) {
    const alle = SEITEN_JE_ROLLE[rolle] ?? []
    return alle.filter((s) => s !== 'stundenplan' || daten?.stundenplan?.configured)
}

/** Nummer einer Seite (ab 1) in der vollen Liste der Rolle — so wird sie gespeichert. */
export function seitenNummer(rolle, seite) {
    return (SEITEN_JE_ROLLE[rolle] ?? []).indexOf(seite) + 1
}

/**
 * Index in `seiten`, an dem ein Durchgang beginnt: bei „später“ dort, wo er stehen blieb (oder
 * der nächsten noch gezeigten Seite), sonst vorn — auch nach „erledigt“, wer ihn erneut aufruft.
 */
export function startIndex(rolle, seiten, daten) {
    if (daten?.stand !== 'spaeter' || !daten?.seite) return 0
    const i = seiten.findIndex((s) => seitenNummer(rolle, s) >= daten.seite)
    return i < 0 ? 0 : i
}

/** „3 von 6“ */
export function fortschritt(index, seiten) {
    return `${index + 1} von ${seiten.length}`
}

/**
 * Geht der Dialog von selbst auf? Nur wenn fällig — und nicht in der Hilfe (F3): Wer dort
 * liest, soll nicht unterbrochen werden; der Dialog kommt auf der nächsten Seite.
 */
export function sollAufgehen(daten, pfad) {
    return Boolean(daten?.faellig) && !String(pfad ?? '').startsWith('/help')
}

// ── Texte der Seiten (Schritt 4) ─────────────────────────────────────────────


export const ERSCHEINUNGSBILDER = [
    { wert: 'light', name: 'Hell' },
    { wert: 'dark', name: 'Dunkel' },
    { wert: 'system', name: 'System' },
]

/** Die Stufe, ab der „Planung“ in der Seitenleiste steht — `null`, wenn der Zuschnitt sie nicht kennt. */
export function planungsStufe(registry) {
    return registry?.stufen?.find((s) => s.eintraege?.includes('planner'))?.stufe ?? null
}

/** Budget in Sätzen — mit den eigenen Zahlen, ohne sie, wenn die Antwort fehlt. */
export function budgetText(b) {
    const stand = typeof b?.remaining_eur === 'number'
        ? einheitenText(ausEuro(b.remaining_eur, b?.einheiten_je_euro ?? undefined))
        : null
    const saetze = [
        stand ? `Gerade hast du ${stand}.` : 'Dein Guthaben wächst jede Unterrichtswoche.',
        zuwachsText(b),
        uebertragText(b),
        'Den Stand siehst du unten in der Seitenleiste.',
    ]
    return saetze.filter(Boolean).join(' ')
}

/**
 * Seite „Gut zu wissen“: vier Absätze, Fristen aus den Löschläufen (`daten.fristen`).
 * Der Hinweis der Schule (`daten.hinweis`, Markdown) steht im Dialog darunter.
 */
export function gutZuWissen(daten, budget) {
    const chat = daten?.fristen?.chat_tage
    const konto = daten?.fristen?.konto_tage
    return [
        {
            titel: 'Keine echten Namen in den Chat.',
            text: 'Die Plattform kennt deinen Namen nicht und gibt ihn nicht weiter — aber was du ' +
                'tippst, geht an den KI-Anbieter. Vor dem Senden warnt sie, wenn sie Namen oder ' +
                'Kontaktdaten erkennt; verlassen solltest du dich darauf nicht.',
            links: [
                { text: 'Datenschutz', href: '/help/datenschutz' },
                { text: 'Nutzungsregeln', href: '/info/regeln' },
            ],
        },
        {
            titel: 'Ein Werkzeug, kein Archiv.',
            text: `Chats werden nach ${chat} Tagen ohne neue Nachricht gelöscht. Was bleiben soll, ` +
                'speicherst du in der Werkstatt oder kopierst es heraus.',
        },
        {
            titel: 'Wer lange nicht da ist, verliert sein Konto.',
            text: `Nach ${konto} Tagen ohne Anmeldung wird es gelöscht — mit Chats, Werkstatt und ` +
                'privaten Bausteinen. Was du mit einer Gruppe oder der Schule teilst, auch die ' +
                'Planung, bleibt.',
        },
        { titel: 'Budget.', text: budgetText(budget) },
    ]
}

/**
 * Seite „Fertig“: was eingerichtet ist — der **tatsächliche** Stand, nicht welche Seiten man
 * übersprungen hat. `nachholen`: wo es sich später einstellen lässt.
 */
export function fertigZeilen({ theme, stufe, stufen, kuerzelGesetzt, stundenplan, gruppen }) {
    const zeilen = []
    const bild = ERSCHEINUNGSBILDER.find((e) => e.wert === theme)?.name ?? 'System'
    zeilen.push({ ok: true, text: `Erscheinungsbild: ${bild}`, nachholen: 'Profil' })
    const s = stufen?.find((x) => x.stufe === stufe)
    if (s) zeilen.push({ ok: true, text: `Umfang: Stufe ${s.stufe} – ${s.name}`, nachholen: 'Profil' })
    if (stundenplan) {
        zeilen.push(kuerzelGesetzt
            ? { ok: true, text: 'Stundenplan-Kürzel gewählt', nachholen: 'Unterricht' }
            : { ok: false, text: 'Kein Stundenplan-Kürzel gewählt', nachholen: 'Unterricht' })
    }
    zeilen.push(gruppen > 0
        ? { ok: true, text: gruppen === 1 ? '1 Unterrichtsgruppe' : `${gruppen} Unterrichtsgruppen`, nachholen: 'Unterricht' }
        : { ok: false, text: 'Noch keine Unterrichtsgruppe', nachholen: 'Unterricht' })
    return zeilen
}

/** Drei Wege weiter; ab der Planungsstufe ersetzt „Planung“ den Assistenten. */
export function wegeWeiter(stufe, abPlanung) {
    const planung = abPlanung != null && stufe != null && stufe >= abPlanung
    return [
        planung
            ? { text: 'Zur Planung', href: '/planning' }
            : { text: 'Einen Assistenten ausprobieren', href: '/assistants' },
        { text: 'Die ersten 30 Minuten', href: '/help/erste-30-minuten' },
        { text: 'Feedback geben', aktion: 'feedback' },
    ]
}
