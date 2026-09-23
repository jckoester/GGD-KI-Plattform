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
    const inhalt = s.thema || s.ue_titel
    if (inhalt) teile.push(inhalt)
    return teile.join(" · ")
}

/** Das Kennzeichen einer Stunde — `null`, wenn es regulärer Unterricht ist. */
export function kennzeichen(s) {
    return KENNZEICHEN[s?.kategorie] ?? null
}

/**
 * Was die Stunde als Nächstes braucht.
 *
 * ⚠️ **Ohne Einheit kann kein Entwurf entstehen** — der Endpunkt dafür hängt an der
 * Unterrichtseinheit. Eine Schaltfläche anzubieten, die 404 antwortet, wäre schlimmer
 * als keine.
 */
export function naechsterSchritt(s) {
    if (s.hat_entwurf) return { text: "Entwurf öffnen", moeglich: true }
    if (!s.ue_node_id) return { text: "Erst einer Einheit zuordnen", moeglich: false }
    return { text: "Entwurf anlegen", moeglich: true }
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
