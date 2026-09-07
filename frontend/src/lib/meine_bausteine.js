/**
 * Ansichtslogik für „Meine Bausteine" (`/knowledge/mine`, AP7 Schritt 2).
 *
 * Hier steht, was sich ohne Browser prüfen lässt: Beschriftungen, Warnstufen,
 * Typ-Filter. Die Komponente daneben bleibt Darstellung. Projektkonvention —
 * Komponententests gibt es nicht, also gehört alles Entscheidbare hierher.
 */

/** Ab wie vielen Tagen bis zum Ablauf die Warnfarbe greift (A4, wie im Backend). */
export const WARNUNG_AB_TAGEN = 14

/**
 * Tage bis zum Ablaufdatum — negativ, wenn es vorbei ist.
 *
 * Gerechnet wird auf **Kalendertage**, nicht auf 24-Stunden-Schritte: Ein Datum
 * „morgen" soll 1 ergeben, egal ob gerade 23 Uhr oder 1 Uhr ist. Ohne das
 * Normalisieren auf Mitternacht sprünge die Zahl im Tagesverlauf.
 *
 * @param {string|null} valid_until ISO-Datum (`YYYY-MM-DD`)
 * @param {Date} [heute]
 * @returns {number|null} null, wenn kein Datum gesetzt ist
 */
export function tageBisAblauf(valid_until, heute = new Date()) {
    if (!valid_until) return null
    const ziel = new Date(`${valid_until}T00:00:00`)
    if (Number.isNaN(ziel.getTime())) return null
    const heuteMitternacht = new Date(heute.getFullYear(), heute.getMonth(), heute.getDate())
    return Math.round((ziel - heuteMitternacht) / 86400000)
}

/**
 * Beschriftung und Warnstufe für die Ablauf-Spalte.
 *
 * Drei Stufen: `keine` (weit weg oder ohne Datum), `warnung` (≤ 14 Tage),
 * `abgelaufen`. Die Stufe entscheidet die Farbe, der Text steht daneben.
 *
 * @returns {{text: string, stufe: 'keine'|'warnung'|'abgelaufen'}}
 */
export function ablaufAnzeige(valid_until, heute = new Date()) {
    const tage = tageBisAblauf(valid_until, heute)
    if (tage === null) return { text: '', stufe: 'keine' }

    const datum = new Date(`${valid_until}T00:00:00`).toLocaleDateString('de-DE')
    if (tage < 0) return { text: `abgelaufen am ${datum}`, stufe: 'abgelaufen' }
    if (tage === 0) return { text: `läuft heute ab`, stufe: 'warnung' }
    if (tage <= WARNUNG_AB_TAGEN) {
        return { text: `läuft ab am ${datum} (in ${tage} ${tage === 1 ? 'Tag' : 'Tagen'})`, stufe: 'warnung' }
    }
    return { text: `läuft ab am ${datum}`, stufe: 'keine' }
}

/**
 * Die im Bestand vorkommenden Typen, für den Typ-Filter.
 *
 * Aus den geladenen Daten abgeleitet statt aus der Taxonomie: Ein Filter, der
 * Typen anbietet, die niemand besitzt, führt in leere Listen. Sortiert nach
 * Label, damit die Reihenfolge nicht von der Fachgruppierung abhängt.
 *
 * @param {{abschnitte: Array}} daten
 * @param {(typ: string) => string} label
 * @returns {Array<{typ: string, label: string, anzahl: number}>}
 */
export function vorkommendeTypen(daten, label = (t) => t) {
    const zaehler = new Map()
    for (const abschnitt of daten?.abschnitte ?? []) {
        for (const baustein of abschnitt.bausteine ?? []) {
            const typ = baustein.content_type ?? ''
            zaehler.set(typ, (zaehler.get(typ) ?? 0) + 1)
        }
    }
    return [...zaehler.entries()]
        .map(([typ, anzahl]) => ({ typ, label: label(typ), anzahl }))
        .sort((a, b) => a.label.localeCompare(b.label, 'de'))
}

/**
 * Filtert die Abschnitte auf einen Typ und wirft leer gewordene weg.
 *
 * Clientseitig, weil der Bestand einer Person klein ist und ein Serverlauf je
 * Klick sich nicht lohnt. Der Endpunkt kann es trotzdem (`?content_type=`) —
 * gebraucht wird das, sobald jemand mehr Bausteine hat, als eine Seite trägt.
 */
export function nachTypGefiltert(daten, typ) {
    if (!typ) return daten
    const abschnitte = (daten?.abschnitte ?? [])
        .map((a) => ({
            ...a,
            bausteine: (a.bausteine ?? []).filter((b) => (b.content_type ?? '') === typ),
        }))
        .filter((a) => a.bausteine.length > 0)
        .map((a) => ({ ...a, anzahl: a.bausteine.length }))

    return {
        ...daten,
        abschnitte,
        gesamt: abschnitte.reduce((summe, a) => summe + a.bausteine.length, 0),
    }
}

/** Beschriftung eines Fachabschnitts — `null` ist „Ohne Fach" (A4). */
export function abschnittsTitel(abschnitt) {
    return abschnitt?.fach ?? 'Ohne Fach'
}

/**
 * Text des Warnbanners: „x Bausteine brauchen Aufmerksamkeit: y …, z …".
 *
 * Nur belegte Kategorien werden genannt — eine Aufzählung mit „0 sind abgelaufen"
 * liest sich wie ein Vorwurf und verlängert den Satz ohne Gewinn.
 *
 * Die Gesamtzahl kommt aus `gesamt` und ist **nicht** die Summe der Kategorien:
 * Ein Baustein kann in mehreren zugleich stecken und zählt einmal.
 *
 * @param {{gesamt: number, laeuft_bald_ab: number, abgelaufen: number,
 *          archivierte_referenzen: number, unvollstaendig: number}} zahlen
 * @returns {string} leer, wenn nichts ansteht — dann erscheint kein Banner
 */
export function aufmerksamkeitsText(zahlen) {
    const gesamt = zahlen?.gesamt ?? 0
    if (!gesamt) return ''

    const teile = []
    const n = (k) => zahlen?.[k] ?? 0
    if (n('laeuft_bald_ab'))
        teile.push(`${n('laeuft_bald_ab')} ${n('laeuft_bald_ab') === 1 ? 'läuft' : 'laufen'} bald ab`)
    if (n('abgelaufen'))
        teile.push(`${n('abgelaufen')} ${n('abgelaufen') === 1 ? 'ist' : 'sind'} abgelaufen`)
    if (n('archivierte_referenzen'))
        teile.push(
            `${n('archivierte_referenzen')} ${n('archivierte_referenzen') === 1 ? 'verweist' : 'verweisen'} auf archivierte Bausteine`,
        )
    if (n('unvollstaendig'))
        teile.push(`${n('unvollstaendig')} ${n('unvollstaendig') === 1 ? 'ist' : 'sind'} unvollständig`)

    const kopf = `${gesamt} ${gesamt === 1 ? 'Baustein braucht' : 'Bausteine brauchen'} Aufmerksamkeit`
    return teile.length ? `${kopf}: ${teile.join(', ')}` : kopf
}

/**
 * Was an einer Zeile angeboten wird.
 *
 * **Archivieren und Reaktivieren sind nicht symmetrisch.** Ein Baustein, der wegen
 * abgelaufenem Datum eingesammelt wurde, trüge nach einem bloßen „wieder aktiv"
 * weiterhin sein altes Datum — der nächtliche Lauf holte ihn in derselben Nacht
 * zurück. Deshalb gibt es dafür den eigenen Weg, der ein neues Datum setzt.
 *
 * Das **Rückgängig** nach dem Archivieren ist wiederum *kein* Reaktivieren: Es soll
 * den Zustand von davor herstellen, also ohne neues Ablaufdatum.
 *
 * @returns {{archivieren: boolean, reaktivieren: boolean, ablauf: boolean}}
 */
export function aktionenFuer(baustein) {
    const archiviert = baustein?.status === 'archived'
    return {
        archivieren: !archiviert,
        reaktivieren: archiviert,
        // Ein Ablaufdatum am archivierten Baustein zu ändern hilft nicht — er ist
        // schon weg. Der Weg zurück ist Reaktivieren, das eins vorschlägt.
        ablauf: !archiviert,
    }
}

/**
 * Lesbare Begründung, wenn das Löschen an fremden Verweisen scheitert (F7, ADR-019).
 *
 * Der Server antwortet mit 409 und einem Objekt aus `nachricht` und `referenzen`.
 * Ältere Fehler (und alle anderen Endpunkte) liefern schlichten Text — beides muss
 * hier ankommen, sonst steht im Dialog `[object Object]`.
 *
 * @returns {{nachricht: string, referenzen: Array}}
 */
export function loeschHindernis(fehler) {
    const detail = fehler?.detail ?? fehler?.message
    if (detail && typeof detail === 'object') {
        return {
            nachricht: detail.nachricht ?? 'Der Baustein lässt sich nicht löschen.',
            referenzen: detail.referenzen ?? [],
        }
    }
    return {
        nachricht: typeof detail === 'string' && detail ? detail : 'Der Baustein lässt sich nicht löschen.',
        referenzen: [],
    }
}

/**
 * Filtert auf die Bausteine, die Aufmerksamkeit brauchen — der Knopf am Banner.
 *
 * Clientseitig wie der Typ-Filter: Der Bestand einer Person ist klein, und ein
 * Serverlauf je Klick lohnt nicht. Der Endpunkt kann es ebenfalls
 * (`?nur_aufmerksamkeit=true`) — gebraucht wird das, sobald Listen länger werden
 * als eine Seite.
 */
export function nurAufmerksamkeit(daten) {
    const abschnitte = (daten?.abschnitte ?? [])
        .map((a) => ({
            ...a,
            bausteine: (a.bausteine ?? []).filter((b) => (b.kategorien ?? []).length > 0),
        }))
        .filter((a) => a.bausteine.length > 0)
        .map((a) => ({ ...a, anzahl: a.bausteine.length }))

    return {
        ...daten,
        abschnitte,
        gesamt: abschnitte.reduce((summe, a) => summe + a.bausteine.length, 0),
    }
}
