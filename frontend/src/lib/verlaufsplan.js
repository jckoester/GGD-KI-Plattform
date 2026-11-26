/**
 * Jahresverlaufspläne der Fachschaften (Päckchen BD, Schritt 5) — reine Funktionen für Ansicht
 * und Editor.
 *
 * Gerechnet wird im Backend (`app/planning/verlaufsplan_zeit.py`): Der Plan speichert nur
 * Reihenfolge und Dauer, der Server legt ihn auf den Kalender des Schuljahrs und liefert die
 * Lage mit (`lage`). Hier liegt nur, was die Oberfläche daraus macht.
 */
import { ueColorIndex } from './planner.js'

/** Richtgröße eines Abschnitts (BD F2): mehr ist erlaubt, wird aber gekennzeichnet. */
export const RICHTGROESSE = 6

/** „15.09.“ aus „2025-09-15“. */
export function tagText(iso) {
    if (!iso) return ''
    const [, m, d] = String(iso).split('-')
    return `${d}.${m}.`
}

/** „15.09.–10.10.“, bei einer Woche ohne Bis nur der Anfang. */
export function zeitraumText(lage) {
    if (!lage?.beginn) return ''
    const von = tagText(lage.beginn)
    const bis = tagText(lage.ende)
    return von === bis ? von : `${von}–${bis}`
}

/** „Woche 5–10“ oder „Woche 5“. */
export function wochenText(lage) {
    if (!lage) return ''
    return lage.von_woche === lage.bis_woche ? `Woche ${lage.von_woche}` : `Woche ${lage.von_woche}–${lage.bis_woche}`
}

/** Was neben einem Abschnitt steht: Ferien, Halbjahr, Länge, Überhang. */
export function hinweise(lage) {
    if (!lage) return []
    const aus = []
    for (const f of lage.ueber_ferien ?? []) aus.push(`über die ${f}`)
    if (lage.vor_ferien) aus.push(`endet vor den ${lage.vor_ferien}`)
    if (lage.halbjahreswechsel) aus.push('Halbjahreswechsel')
    if (lage.lang) aus.push(`länger als ${RICHTGROESSE} Wochen`)
    if (lage.ausserhalb) aus.push(`${lage.ausserhalb} ${lage.ausserhalb === 1 ? 'Woche' : 'Wochen'} nach Schuljahresende`)
    return aus
}

/**
 * Wie viele Wochen ein Abschnitt dauern muss, der in Woche `vonWoche` beginnt und an den
 * nächsten Ferien enden soll (Knopf „bis zu den Ferien“, BD F3). `null` ohne Kalender.
 */
export function wochenBisZuDenFerien(vonWoche, ferienabschnitte) {
    for (const f of ferienabschnitte ?? []) {
        if (f.von_woche <= vonWoche && vonWoche <= f.bis_woche) return f.bis_woche - vonWoche + 1
    }
    return null
}

/** Planungsart (BD Schritt 7): Abschnitte nennen Lernsequenzen (Vorgabe) oder Kapitel. */
export const PLANUNGSARTEN = [
    { wert: 'sequenz', text: 'sequenzgenau' },
    { wert: 'kapitel', text: 'kapitelgenau' },
]

/** Das Feld eines Abschnitts, das zur Planungsart gehört. */
export function bezugsfeld(planungsart) {
    return planungsart === 'sequenz' ? 'sequenz_ids' : 'kapitel_ids'
}

/**
 * Was die Curricula der Stufe für die Auswahl hergeben: Kapitel in Reihenfolge, je Sequenz ihr
 * Kapitel, Titel und Stunden je ID — eine Stelle für Editor, Tabelle und Farben.
 */
export function einheiten(curricula) {
    const kapitelReihenfolge = []
    const kapitelVon = {}
    const titel = {}
    const std = {}
    for (const c of curricula ?? []) {
        for (const k of c.kapitel ?? []) {
            kapitelReihenfolge.push(k.id)
            titel[k.id] = k.titel
            std[k.id] = k.std ?? null
            for (const sq of k.sequenzen ?? []) {
                kapitelVon[sq.id] = k.id
                titel[sq.id] = sq.titel
                std[sq.id] = sq.std ?? null
            }
        }
    }
    return { kapitelReihenfolge, kapitelVon, titel, std }
}

/** Das erste Kapitel eines Abschnitts — bei Sequenzen das Kapitel der ersten Sequenz. */
export function erstesKapitel(abschnitt, planungsart, kapitelVon = {}) {
    const erste = abschnitt?.[bezugsfeld(planungsart)]?.[0]
    if (!erste) return null
    return planungsart === 'sequenz' ? (kapitelVon[erste] ?? null) : String(erste)
}

/** Farbe eines Abschnitts: die seines ersten Kapitels in der Reihenfolge des Curriculums. */
export function abschnittFarbe(abschnitt, kapitelReihenfolge, { planungsart = 'kapitel', kapitelVon = {}, dark = false } = {}) {
    const kap = erstesKapitel(abschnitt, planungsart, kapitelVon)
    const i = kap ? kapitelReihenfolge.indexOf(kap) : -1
    return i < 0 ? null : ueColorIndex(i, dark)
}

/**
 * Dauervorschlag aus Stunden (Jan, 25.11.2026): `aufrunden(Stunden ÷ Wochenstunden)`, mindestens 1.
 * `null`, wenn Stunden oder Wochenstunden fehlen.
 */
export function dauerVorschlag(stunden, wochenstunden) {
    if (!stunden || !wochenstunden) return null
    return Math.max(1, Math.ceil(stunden / wochenstunden))
}

/** Bezeichnung der Bezüge eines Abschnitts, für Tabelle und Auswahl. */
export function bezugText(abschnitt, planungsart, titel) {
    if (abschnitt?.puffer) return 'Puffer'
    return (abschnitt?.[bezugsfeld(planungsart)] ?? []).map((id) => titel[id] ?? 'nicht mehr im Curriculum').join(', ')
}

/** Eine neue, leere Zeile: eine Woche; wählt man Sequenzen oder Kapitel, schlägt der Editor die Dauer vor. */
export const VORGABE_WOCHEN = 1
export function neuerAbschnitt() {
    return { id: null, titel: '', wochen: VORGABE_WOCHEN, kapitel_ids: [], sequenz_ids: [], notiz: '', puffer: false }
}

/**
 * Puffer an- oder abwählen (zweiter Durchgang, Jan 25.11.2026) — derselbe Weg wie eine Sequenz
 * oder ein Kapitel, aber ausschließend: Ein Puffer nennt nichts aus dem Curriculum und heißt ohne
 * eigenen Titel „Puffer“. Beim Abwählen verschwindet nur dieser vorgegebene Titel.
 */
export const PUFFER_TITEL = 'Puffer'
export function pufferUmschalten(a) {
    if (a.puffer) return { ...a, puffer: false, titel: a.titel === PUFFER_TITEL ? '' : a.titel }
    return { ...a, puffer: true, kapitel_ids: [], sequenz_ids: [], titel: a.titel?.trim() ? a.titel : PUFFER_TITEL }
}

/** Abschnitt `i` um `schritt` Plätze verschieben (−1 hoch, +1 runter); am Rand unverändert. */
export function verschieben(liste, i, schritt) {
    const j = i + schritt
    if (i < 0 || i >= liste.length || j < 0 || j >= liste.length) return liste
    const neu = [...liste]
    const [a] = neu.splice(i, 1)
    neu.splice(j, 0, a)
    return neu
}

/** Abschnitt von Platz `von` an Platz `nach` (Ziehen). */
export function umsetzen(liste, von, nach) {
    if (von === nach || von < 0 || nach < 0 || von >= liste.length || nach >= liste.length) return liste
    const neu = [...liste]
    const [a] = neu.splice(von, 1)
    neu.splice(nach, 0, a)
    return neu
}

/** Laufendes und nächstes Schuljahr — mehr wird nicht neu angelegt. */
export function schuljahreZumAnlegen(aktuell) {
    if (!/^\d{4}\/\d{2}$/.test(aktuell ?? '')) return []
    const start = Number(aktuell.slice(0, 4)) + 1
    return [aktuell, `${start}/${String((start + 1) % 100).padStart(2, '0')}`]
}

/** Wohin sich ein Plan übernehmen lässt: laufendes und nächstes Schuljahr, ohne sein eigenes. */
export function uebernahmeZiele(aktuell, eigenes) {
    return schuljahreZumAnlegen(aktuell).filter((j) => j !== eigenes)
}

/** Pläne, die sich als Ausgangspunkt für einen neuen Plan anbieten: gleiches Fach, gleiche
 *  Stufe, anderes Schuljahr, neueste zuerst (Schritt 6). */
export function ausgangspunkte(plaene, fachId, stufe, schuljahr) {
    if (!stufe) return []
    return (plaene ?? [])
        .filter((p) => p.subject_id === fachId && p.stufe === stufe && p.schuljahr !== schuljahr)
        .sort((a, b) => (a.schuljahr < b.schuljahr ? 1 : -1))
}

/** Pläne eines Fachs: laufende und kommende vorn, das Archiv getrennt (BD F10). */
export function teilen(plaene) {
    const aktuell = []
    const archiv = []
    for (const p of plaene ?? []) (p.archiviert ? archiv : aktuell).push(p)
    const ordnung = (a, b) => (a.schuljahr === b.schuljahr ? (a.stufe ?? 0) - (b.stufe ?? 0)
        : (a.schuljahr < b.schuljahr ? -1 : 1))
    return { aktuell: aktuell.sort(ordnung), archiv: archiv.sort((a, b) => -ordnung(a, b)) }
}

/**
 * Laufende und kommende Pläne nach Schuljahr gruppiert, darin nach Stufe (Übersicht, Schritt 7).
 * `[{ schuljahr, text, plaene }]`; `text` sagt „laufendes“ oder „kommendes Schuljahr“.
 */
export function nachSchuljahr(plaene, aktuell) {
    const gruppen = new Map()
    for (const p of plaene ?? []) {
        if (!gruppen.has(p.schuljahr)) gruppen.set(p.schuljahr, [])
        gruppen.get(p.schuljahr).push(p)
    }
    return [...gruppen.entries()]
        .sort(([a], [b]) => (a < b ? -1 : 1))
        .map(([schuljahr, liste]) => ({
            schuljahr,
            text: schuljahr === aktuell ? 'laufendes Schuljahr' : schuljahr > aktuell ? 'kommendes Schuljahr' : '',
            plaene: [...liste].sort((x, y) => (x.stufe ?? 0) - (y.stufe ?? 0)),
        }))
}

/** Grauer Zusatz einer Planzeile: Beschluss, verplante Wochen, Planungsart. */
export function zeilenZusatz(p) {
    const teile = []
    if (p.status !== 'draft') {
        teile.push(p.beschlossen_am ? `beschlossen am ${p.beschlossen_am.split('-').reverse().join('.')}` : 'beschlossen')
    }
    teile.push(`${p.wochen} ${p.wochen === 1 ? 'Woche' : 'Wochen'} geplant`)
    teile.push(p.planungsart === 'sequenz' ? 'sequenzgenau' : 'kapitelgenau')
    return ' · ' + teile.join(' · ')
}

/**
 * Verweise aus einem Curriculum auf die Jahresverlaufspläne seiner Stufen im laufenden Schuljahr
 * (Schritt 7, Unterschritt 10). Je Stufe mit Plan ein Link; gibt es keinen, ein Link auf die Liste
 * des Fachs. `[{ href, text }]`.
 */
export function planVerweise(plaene, { fachId, stufen = [], aktuell }) {
    const treffer = stufen
        .map((st) => (plaene ?? []).find((p) => p.subject_id === fachId && p.stufe === st && p.schuljahr === aktuell))
        .filter(Boolean)
    if (!treffer.length) return [{ href: `/knowledge/year-plans?fach=${fachId}`, text: 'Jahresverlaufspläne' }]
    const mehrere = treffer.length > 1
    return treffer.map((p) => ({
        href: `/knowledge/year-plans/${p.id}`,
        text: mehrere ? `Jahresverlaufsplan Kl. ${p.stufe}` : 'Jahresverlaufsplan',
    }))
}

/**
 * Hinweis über einem Plan im Entwurf (zweiter Durchgang, Jan 25.11.2026) — wie beim Curriculum
 * (`entwurfHinweis` in `$lib/curriculum.js`), je nachdem, ob man ihn bearbeiten darf. Leer, wenn
 * der Plan beschlossen ist.
 */
export const ENTWURF_HINWEIS =
    'Entwurf: Alle Lehrkräfte können ihn lesen, bearbeiten kann ihn die Fachschaft. Beschlossen ist er, sobald jemand aus der Fachschaft „Beschließen“ wählt.'
export const ENTWURF_NUR_LESEN =
    'Entwurf — nur lesen. Die Fachschaft des Fachs hat den Plan noch nicht beschlossen; er kann sich noch ändern.'

export function entwurfHinweis(plan) {
    if (plan?.status !== 'draft') return ''
    return plan.darf_bearbeiten ? ENTWURF_HINWEIS : ENTWURF_NUR_LESEN
}

/** Bilanz eines Kapitels: „passt“, „zu wenig“, „zu viel“ oder `null` ohne Zahlen. Ein Spielraum
 *  von einer Wochenstunde gilt als passend. */
export function bilanzStand(kapitel, wochenstunden) {
    if (kapitel?.soll == null || kapitel?.geplant == null) return null
    const spiel = wochenstunden || 0
    if (kapitel.geplant < kapitel.soll - spiel) return 'zu wenig'
    if (kapitel.geplant > kapitel.soll + spiel) return 'zu viel'
    return 'passt'
}

/** Der Plan, wie ihn `PUT` erwartet — ohne berechnete Felder. */
export function zumSpeichern(abschnitte, planungsart) {
    return {
        planungsart: planungsart ?? 'kapitel',
        abschnitte: (abschnitte ?? []).map((a) => ({
            id: a.id ?? null,
            titel: a.titel ?? '',
            wochen: Number(a.wochen) || 1,
            kapitel_ids: [...(a.kapitel_ids ?? [])],
            sequenz_ids: [...(a.sequenz_ids ?? [])],
            notiz: a.notiz ?? '',
            puffer: !!a.puffer,
        })),
    }
}

// ── Spur im Planer der Gruppe (BD Teil B, Schritt 2) ─────────────────────────

/** Gemerkt in den Einstellungen: ob die Ablaufleiste im Planer eingeklappt ist. */
export const SPUR_SCHLUESSEL = 'verlaufsplan_spur_zu'

/**
 * Der Satz, wenn eine Gruppe keinen Plan hat (Antwort von `GET /planning/groups/{id}/verlaufsplan`).
 * Leer, wenn es einen Plan gibt oder die Gruppe kein Fach hat — dann zeigt der Planer gar nichts.
 */
export function spurOhnePlan(antwort, fachName = '') {
    if (!antwort || antwort.plan) return ''
    const fach = fachName ? ` in ${fachName}` : ''
    if (antwort.grund === 'kein_plan') {
        return `Für Klasse ${antwort.stufe}${fach} gibt es im Schuljahr ${antwort.schuljahr} noch keinen Jahresverlaufsplan der Fachschaft.`
    }
    if (antwort.grund === 'keine_stufe') {
        return 'Die Klassenstufe dieser Gruppe ist nicht bekannt, deshalb fehlt der Jahresverlaufsplan der Fachschaft. Du kannst sie unter Unterricht festlegen.'
    }
    return ''
}

/** Kopfzeile der Spur: „Klasse 9 · beschlossen am 03.10.“ bzw. „Klasse 9 · Entwurf“. */
export function spurKopf(plan) {
    if (!plan) return ''
    const stand = plan.status === 'draft' ? 'Entwurf' : plan.beschlossen_am ? `beschlossen am ${tagText(plan.beschlossen_am)}` : 'beschlossen'
    return `Klasse ${plan.stufe} · ${stand}`
}

/**
 * Thema des Plans je Planerwoche: `{ '2026-W38': {nr, titel, puffer, farbe} }`. Die Zuordnung
 * Woche → Abschnitt rechnet der Server (`abschnitt_je_woche`, ISO-Woche wie `wochenSchluessel`).
 */
export function wochenThemen(antwort) {
    const plan = antwort?.plan
    if (!plan) return {}
    const { kapitelReihenfolge, kapitelVon } = einheiten(plan.curricula)
    const ergebnis = {}
    for (const [woche, i] of Object.entries(antwort.abschnitt_je_woche ?? {})) {
        const a = plan.abschnitte?.[i]
        if (!a) continue
        ergebnis[woche] = {
            nr: i + 1,
            titel: a.puffer ? (a.titel || PUFFER_TITEL) : (a.titel || 'ohne Thema'),
            puffer: !!a.puffer,
            farbe: a.puffer ? null : abschnittFarbe(a, kapitelReihenfolge, { planungsart: plan.planungsart, kapitelVon }),
        }
    }
    return ergebnis
}

// ── Einheiten aus dem Plan anlegen (BD Teil B, Schritt 5) ─────────────────────

/** Warum ein Abschnitt keine Einheit bekommt (`grund` der Vorschau). */
export const GRUND_TEXT = {
    puffer: 'Puffer — keine Einheit',
    kapitel_vorhanden: 'übersprungen: Kapitel hat schon eine Einheit',
    schon_angelegt: 'schon aus dem Plan angelegt',
    vorbei: 'übersprungen: liegt in der Vergangenheit',
    nach_schuljahresende: 'übersprungen: liegt nach dem Schuljahresende',
    belegt: 'übersprungen: Stunden dieser Wochen schon belegt',
}

/** „4 Stunden“, „1 Stunde“, „keine Stunde“. */
export function stundenText(n) {
    if (!n) return 'keine Stunde'
    return n === 1 ? '1 Stunde' : `${n} Stunden`
}

/** „3 Einheiten“, „1 Einheit“. */
export function einheitenText(n) {
    return n === 1 ? '1 Einheit' : `${n} Einheiten`
}

/** Was in der Zeile eines Vorschlags rechts steht. */
export function vorschlagStand(v) {
    if (!v.anlegen) return GRUND_TEXT[v.grund] ?? 'übersprungen'
    if (v.ohne_termine) return 'neu, noch ohne Termine'
    return `neu, belegt ${stundenText(v.stunden)}`
}

/** Hinweise zu einem neuen Vorschlag: Kapitel nicht mehr im Curriculum, belegte Stunden. */
export function vorschlagHinweise(v) {
    const h = []
    if (v.anlegen && v.kapitel_fehlt) h.push('Das Kapitel ist nicht mehr im Curriculum; die Einheit bekommt keins.')
    if (v.anlegen && v.belegt) h.push(`${stundenText(v.belegt)} in diesen Wochen ${v.belegt === 1 ? 'ist' : 'sind'} schon belegt und ${v.belegt === 1 ? 'bleibt' : 'bleiben'}, wie ${v.belegt === 1 ? 'sie ist' : 'sie sind'}.`)
    return h
}

/** Satz unter der Vorschau: „Neu: 3 Einheiten, zusammen 24 Stunden.“ bzw. „…, noch ohne Termine.“ */
export function vorschauSumme(vorschau) {
    if (!vorschau?.neu) return 'Aus diesem Plan ist nichts mehr anzulegen.'
    const teil = vorschau.stunden ? `zusammen ${stundenText(vorschau.stunden)}` : 'noch ohne Termine'
    return `Neu: ${einheitenText(vorschau.neu)}, ${teil}. Danach kannst du das Anlegen rückgängig machen.`
}

/** Beschriftung des Knopfs im Dialog. */
export function anlegenKnopf(vorschau) {
    if (!vorschau?.neu) return 'Nichts anzulegen'
    return `${einheitenText(vorschau.neu)} anlegen`
}

/** Meldung nach dem Anlegen (`{einheiten, stunden}`). */
export function laufMeldung(lauf) {
    if (!lauf?.einheiten) return 'Es gab nichts anzulegen.'
    const teil = lauf.stunden ? `, ${stundenText(lauf.stunden)} belegt` : ''
    return `${einheitenText(lauf.einheiten)} aus dem Jahresverlaufsplan angelegt${teil}.`
}
