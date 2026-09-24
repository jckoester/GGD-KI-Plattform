/**
 * Texte und Regeln für die Tageskacheln der Startseite (AP3).
 *
 * Die Logik steht hier, weil das Projekt keine Svelte-Komponententests hat — und weil
 * die **leeren Zustände** der eigentliche Inhalt dieser Kacheln sind: An den meisten
 * Tagen des Schuljahres ist mindestens eine der beiden leer.
 */

/** Kategorien, die eine Stunde als besonders kennzeichnen. */
const KENNZEICHEN = {
    ausfall: "Ausfall",
    vertretung: "Vertretung",
    pruefung: "Klassenarbeit",
    puffer: "Puffer",
}

/**
 * Der Satz für einen leeren Tag.
 *
 * ⚠️ **Drei Lagen, drei Sätze** — und die Unterscheidung ist der Zweck dieser Funktion.
 * „Heute kein Unterricht" ist eine Feststellung, „Ferien" eine Erklärung, „noch nichts
 * geplant" eine **Aufforderung**. Wer zu Schuljahresbeginn den ersten Satz liest, sucht
 * den Fehler bei sich und findet keinen.
 */
export function leerSatz(tag, lage = {}) {
    if (!lage.hatGruppen) {
        return "Noch keine Unterrichtsgruppen. Legen Sie eine an, dann steht hier Ihr Tag."
    }
    if (!lage.hatPlanung) {
        return "Für Ihre Gruppen sind noch keine Stunden angelegt — dafür braucht es ein Wochenmuster."
    }
    switch (tag?.grund) {
        case "ferien":
            return "Ferien."
        case "feiertag":
            return "Feiertag."
        case "unterrichtsfrei":
            return "Unterrichtsfrei."
        case "wochenende":
            return "Wochenende."
        case "ausserhalb_schuljahr":
            return "Außerhalb des Schuljahres."
        default:
            return "Kein Unterricht."
    }
}

/** Ob der leere Zustand zum Einrichten auffordert — dann gehört ein Weg dorthin daneben. */
export function leerFuehrtZurEinrichtung(lage = {}) {
    return !lage.hatGruppen || !lage.hatPlanung
}

/** Die Überschrift der zweiten Kachel — nie „Morgen". */
export function zweiteUeberschrift(tag) {
    if (!tag) return "Nächster Schultag"
    return `Nächster Schultag · ${alsTagMonat(tag.datum)}`
}

/** Der Satz, wenn es keinen nächsten Schultag mehr gibt. */
export const KEIN_NAECHSTER =
    "Kein weiterer Schultag in diesem Schuljahr."

/**
 * Eine Zeile der Tagesliste.
 *
 * Reihenfolge der Angaben: **Stunde, Gruppe, Thema** — die Stunde zuerst, weil man den
 * Tag danach absucht. Ohne Thema steht die Einheit, ohne beides nichts: Ein Platzhalter
 * wie „kein Thema" füllt Platz, ohne etwas zu sagen.
 */
export function stundenZeile(s) {
    const teile = [s.stunde, s.gruppe]
    const inhalt = stundenTitel(s)
    if (inhalt) teile.push(inhalt)
    return teile.join(" · ")
}

/**
 * Der Vorspann einer Zeile: Stunde und Gruppe — das, was **nicht** verlinkt wird.
 *
 * Getrennt vom Titel, weil die beiden verschiedene Ziele haben: Der Titel führt in den
 * Stundenentwurf, die Zeile als ganze soll nicht zu einer großen Schaltfläche werden.
 */
export function stundenVorspann(s) {
    return [s.stunde, s.gruppe].filter(Boolean).join(" · ")
}

/** Thema oder Einheit — was die Stunde inhaltlich benennt. `null`, wenn nichts dasteht. */
export function stundenTitel(s) {
    return s?.thema || s?.ue_titel || null
}

/** Das Kennzeichen einer Stunde — `null`, wenn es regulärer Unterricht ist. */
export function kennzeichen(s) {
    return KENNZEICHEN[s?.kategorie] ?? null
}

/**
 * Der Stundentitel als Weg — `null`, wenn keiner gebaut werden kann.
 *
 * **Immer ein `<a>`, nie eine Schaltfläche.** Das ist keine Stilfrage, sondern die
 * Bedingung dafür, dass der Titel überhaupt zu sehen ist: Die Zeile steht in einem
 * `truncate`-Container, und `text-overflow: ellipsis` kann **Text** kürzen, aber keinen
 * Inline-Block. Ein `<button>` ist ein atomarer Kasten — er passt ganz oder gar nicht,
 * und wenn er nicht passt, bleibt vom Titel nur das „…". Genau so ist er am 24.09.2026
 * verschwunden, nachdem er vorher als reiner Text lesbar gewesen war.
 *
 * `ziel` ist deshalb **immer** ein sinnvolles Linkziel: der Entwurf, wenn es einen gibt,
 * sonst die Jahresplanung. Ist zusätzlich `slotId` gesetzt, kann der Klick es besser —
 * er legt den Entwurf an und springt hinein. Das `href` bleibt trotzdem echt, damit
 * Mittelklick und „in neuem Tab öffnen" irgendwo landen und nicht ins Leere.
 */
export function titelAktion(s) {
    const basis = plannerLink(s)
    if (!basis) return null
    if (s?.stunde_node_id) {
        return { ziel: `${basis}/lessons/${s.stunde_node_id}`, slotId: null }
    }
    return { ziel: basis, slotId: s?.slot_id ?? null }
}

/**
 * Die Beschriftung des Titels.
 *
 * **Eine Stunde ohne Thema und ohne Einheit hat keinen Titel** — am Anfang des
 * Schuljahres ist das die Mehrheit. Hier steht dann „ohne Thema", nicht „Stunde planen":
 * An der Stelle des Titels gehört eine **Beschreibung**, keine Handlungsaufforderung.
 * Ein Aktionswort an dieser Stelle liest sich wie der Titel der Stunde und drängt sich
 * vor das, was man eigentlich sucht (Jan, 24.09.2026).
 */
export function titelText(s) {
    return stundenTitel(s) ?? "ohne Thema"
}

/**
 * Der Hinweis auf die fehlende Unterrichtseinheit — `null`, wenn sie zugeordnet ist.
 *
 * Er sagt **nichts mehr über den Entwurf**: Den erreicht der Titel selbst, in jedem
 * Zustand. Zwei Bedienelemente derselben Zeile, die dasselbe tun, sind keine Hilfe,
 * sondern eine Frage — welches ist das richtige?
 *
 * Die Zuordnung zur Einheit bleibt ein eigener Schritt, und sie geschieht in der
 * **Jahresplanung**: Dort sieht man, welche Einheiten es gibt und wie sie im Jahr liegen.
 * Ein Hinweis ohne Weg wäre eine Sackgasse — man weiß, was fehlt, aber nicht, wohin.
 */
export function einheitHinweis(s) {
    if (s?.ue_node_id) return null
    return { text: "Erst einer Einheit zuordnen", ziel: plannerLink(s) }
}

/**
 * Der Weg in die Planung dieser Gruppe — `null`, wenn er nicht gebaut werden kann.
 *
 * ⚠️ Die Route lautet `/subjects/{slug}/groups/{id}/planner`. Fehlt der Fach-Slug (eine
 * Gruppe ohne Fach), entstünde `/subjects/null/...` — ein Link, der aussieht, als führe
 * er irgendwohin. Lieber keiner.
 */
export function plannerLink(s) {
    if (!s?.subject_slug || !s?.group_id) return null
    return `/subjects/${s.subject_slug}/groups/${s.group_id}/planner`
}

/**
 * Der Satz über offene Gruppen-Entscheidungen — `null`, wenn keine offen sind.
 *
 * Zwei Quellen, ein Satz: Vorschläge aus dem Stundenplan und Angebote aus dem
 * Schulkonto. Die Lehrkraft unterscheidet sie an dieser Stelle nicht — sie will wissen,
 * ob etwas auf sie wartet. Die Unterscheidung steht dort, wo sie entschieden wird.
 */
export function offeneEntscheidungen(vorschlaege = 0, angebote = 0) {
    const n = (vorschlaege || 0) + (angebote || 0)
    if (!n) return null
    return n === 1
        ? "1 Gruppe wartet auf Ihre Entscheidung"
        : `${n} Gruppen warten auf Ihre Entscheidung`
}

function alsTagMonat(wert) {
    if (!wert) return ""
    const d = new Date(wert)
    return Number.isNaN(d.getTime())
        ? String(wert)
        : d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })
}
