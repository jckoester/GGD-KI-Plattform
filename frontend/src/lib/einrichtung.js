/**
 * Einrichtung beim ersten Login — reine Regeln. Lehrkräfte seit 0.43
 * (`Onboarding-Lehrkraefte-Plan.md`), Schüler:innen seit 0.47 (`Onboarding-Schueler-Plan.md`).
 *
 * Welche Seiten eine Rolle durchgeht, welche entfällt, wo ein Wiedereinstieg beginnt und wann
 * der Dialog von selbst aufgeht. Der Stand kommt von `GET /einrichtung`; Seiteninhalte und
 * Speichern stehen in `EinrichtungDialog.svelte`.
 *
 * **Eine Seite dazunehmen:** Schlüssel in `SEITEN`, Liste in
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
    ki_hilft: { titel: 'So hilft dir die KI' },
    faecher: { titel: 'Deine Fächer' },
    fertig: { titel: 'Fertig' },
}

export const SEITEN_JE_ROLLE = {
    teacher: ['willkommen', 'gut_zu_wissen', 'stufe', 'stundenplan', 'gruppen', 'fertig'],
    student: ['willkommen', 'gut_zu_wissen', 'ki_hilft', 'faecher', 'fertig'],
}

/**
 * Die Rolle, nach der sich die Einrichtung richtet — `null`: keine Einrichtung (reine Admins, F10).
 * Wer Lehrkraft und Schüler:in ist, bekommt die der Lehrkraft (0.47, F9) — wie `ROLLEN` im Backend.
 * In der Vorschau sind die Rollen die simulierten: Die Lehrkraft sieht die Einrichtung ihrer Klasse.
 */
export function einrichtungsRolle(rollen) {
    const r = rollen ?? []
    if (r.includes('teacher')) return 'teacher'
    if (r.includes('student')) return 'student'
    return null
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
            text: 'Die Plattform gibt deinen Namen nicht weiter — aber was du ' +
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

// ── Seiten der Schüler:innen (0.47) ──────────────────────────────────────────
//
// Leserschaft ab Klasse 6 (F3): kurze, klare Sätze ohne Fachwörter, aber nicht kindlich.

/**
 * Seite „Gut zu wissen“ für Schüler:innen: vier Absätze. Fristen aus `daten.fristen`, Budget aus
 * `GET /budget/me`. In der Vorschau ohne `budget` aufrufen — der Endpunkt liefert dort das Budget
 * der Lehrkraft, und deren Zahlen gehören nicht in die Sicht der Klasse.
 */
export function gutZuWissenSchueler(daten, budget) {
    const chat = daten?.fristen?.chat_tage
    const konto = daten?.fristen?.konto_tage
    return [
        {
            titel: 'Keine Namen in den Chat.',
            text: 'Die Plattform gibt deinen Namen nicht an die KI weiter. Was du tippst, geht aber ' +
                'an den KI-Anbieter — schreib deshalb keine Namen, Adressen oder Telefonnummern ' +
                'hinein, auch nicht von anderen. Erkennt die Plattform so etwas, warnt sie dich vor ' +
                'dem Senden.',
            links: [
                { text: 'Datenschutz', href: '/help/datenschutz' },
                { text: 'Nutzungsregeln', href: '/info/regeln' },
            ],
        },
        {
            // F5 a: „niemand“ ohne die Ausnahme wäre nicht ehrlich (Wortlaut wie `docs/user/schueler.md`).
            titel: 'Deine Chats sieht niemand außer dir.',
            text: 'Auch deine Lehrkraft kann sie nicht lesen. Eine Ausnahme gibt es: Schreibst du ' +
                'etwas, das nach einer Notlage klingt, bekommt die Schule einen Hinweis — ohne ' +
                'deinen Namen und ohne den Text — und du siehst Hilfsangebote. Hineinsehen kann ' +
                'erst jemand, wenn zwei Personen der Schule das gemeinsam freigeben.',
        },
        {
            titel: 'Chats bleiben nicht für immer.',
            text: `Ein Chat wird ${chat} Tage nach der letzten Nachricht gelöscht. Was du ` +
                'behalten willst, speicherst du mit „Speichern“ in deiner Werkstatt. Wer sich ' +
                `${konto} Tage nicht anmeldet, verliert sein Konto — mit allem in der Werkstatt.`,
        },
        { titel: 'Budget.', text: budgetText(budget) },
    ]
}

/** Seite „So hilft dir die KI“ (F8): was die Assistenten tun, und dass KI angegeben wird. */
export function kiHilft() {
    return [
        {
            titel: 'Lernen statt abschreiben.',
            text: 'Die Assistenten sind so eingestellt, dass du selbst nachdenkst. Oft fragen sie ' +
                'zurück, statt die Lösung hinzuschreiben — das ist Absicht.',
        },
        {
            titel: 'Assistenten für deine Fächer.',
            text: 'Ein Fachassistent weiß schon, worum es geht, und kennt manchmal, was ihr im ' +
                'Unterricht gemacht habt. Du findest sie unter „Assistenten“ und auf der Seite ' +
                'deines Fachs.',
        },
        {
            titel: 'Vorschläge im Chat.',
            text: 'Fragst du im freien Chat, schlägt dir die Plattform manchmal einen passenden ' +
                'Assistenten vor.',
        },
        {
            titel: 'KI angeben.',
            text: 'Nutzt du KI für eine GFS, ein Referat oder eine Facharbeit, gib das an — wie ' +
                'jede andere Quelle.',
            links: [{ text: 'KI-Ergebnisse zitieren', href: '/help/zitieren' }],
        },
    ]
}

/**
 * Seite „Deine Fächer“ ohne Fach: derselbe Satz wie auf `/subjects`. Im Erprobungsbetrieb wäre
 * „keine Fächer zugeordnet“ unwahr — es gibt sie, sie sind nur nicht freigegeben.
 */
export function faecherLeerText(erprobung) {
    return erprobung
        ? 'Für dich ist noch kein Fach freigegeben. Während der Erprobung sind nur die Fächer der ' +
            'teilnehmenden Lehrkräfte zu sehen.'
        : 'Dir sind noch keine Fächer zugeordnet.'
}

/**
 * Darunter, ob Fächer da sind oder nicht: woher sie kommen und was tun, wenn eins fehlt. Die
 * Regel „erscheint mit Chat oder Fachassistent“ gilt im Erprobungsbetrieb nicht
 * (`fachWirdAngeboten`) — dort fehlt der Satz.
 */
export function fachFehltText(erprobung) {
    return [
        'Deine Fächer kommen aus deinem Schulkonto. Fehlt eins oder steht eins zu viel da, sag es ' +
            'deiner Lehrkraft — hier lässt sich das nicht ändern.',
        erprobung ? null : 'Ein Fach erscheint, sobald es dort einen Assistenten für dich gibt ' +
            'oder du dort chattest.',
        'Hat deine Lehrkraft dir einen Code genannt, trittst du der Gruppe hier bei.',
    ].filter(Boolean).join(' ')
}

/** Seite „Fertig“ der Schüler:innen: drei Wege weiter. */
export function wegeWeiterSchueler() {
    return [
        { text: 'Ersten Chat beginnen', href: '/chat' },
        { text: 'Assistenten ansehen', href: '/assistants' },
        { text: 'Hilfe für Schüler:innen', href: '/help/schueler' },
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

/** Stundenraster auf Seite 5 nur ab der Planungsstufe (F6); ohne bekannte Planungsstufe nie. */
export function rasterAnbieten(stufe, abPlanung) {
    return abPlanung != null && stufe != null && stufe >= abPlanung
}

// ── „Später“ und Wiederaufruf (Schritt 6) ────────────────────────────────────

/** Hinweis auf der Startseite: nur nach „später“, bis abgeschlossen oder weggeklickt (F4 a). */
export function hinweisZeigen(daten) {
    return daten?.stand === 'spaeter'
}

/** „2 von 6 Schritten erledigt“ — erledigt sind die Seiten vor der, an der es weitergeht. */
export function hinweisText(rolle, daten) {
    const seiten = sichtbareSeiten(rolle, daten)
    const i = startIndex(rolle, seiten, daten)
    return `${i} von ${seiten.length} ${seiten.length === 1 ? 'Schritt' : 'Schritten'} erledigt.`
}
