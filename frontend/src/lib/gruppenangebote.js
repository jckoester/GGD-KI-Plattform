/**
 * Texte und Regeln für die Angebote neuer SSO-Unterrichtsgruppen (AP2).
 *
 * Die Logik steht hier, weil das Projekt keine Svelte-Komponententests hat — und weil
 * gerade die Warnung vor dem Zuordnen stimmen muss: Sie ist das Letzte, was eine
 * Lehrkraft liest, bevor zwei Gruppen zusammengeführt werden.
 */

/** Wie eine Gruppe in der Auswahlliste dasteht — Name, Fach und Beleg. */
export function kandidatZeile(k) {
    const teile = [k.name]
    if (k.fach && !k.name.toLowerCase().includes(k.fach.toLowerCase())) teile.push(k.fach)
    return `${teile.join(" · ")} · ${k.beleg}`
}

/**
 * Die Rückfrage vor dem Zuordnen.
 *
 * ⚠️ **Zwei Dinge müssen drinstehen**, sonst führt die Lehrkraft blind zusammen:
 * *welche* Gruppe getroffen wird und *was sich ändert* — ab dann führt das Schulkonto
 * die Mitglieder, und geerbte Mitgliedschaften fallen.
 */
export function zuordnenFrage(angebot, kandidat) {
    return (
        `„${angebot.name}" wird der Gruppe „${kandidat.name}" zugeordnet.\n\n` +
        "Ab dann kommen die Mitglieder aus dem Schulkonto. Wer bisher über die Klasse " +
        "in der Gruppe war, verliert die Mitgliedschaft — Jahresplan, Stundenentwürfe " +
        "und Chats bleiben.\n\nFortfahren?"
    )
}

/** Was nach dem Zuordnen zu berichten ist — nur wenn es etwas zu berichten gibt. */
export function zuordnenErgebnis(antwort) {
    const n = antwort?.geerbte_entfernt ?? 0
    if (!n) return "Die Gruppe ist jetzt mit dem Schulkonto verknüpft."
    return (
        `Die Gruppe ist jetzt mit dem Schulkonto verknüpft. ${n} über die Klasse ` +
        `geerbte ${n === 1 ? "Mitgliedschaft wurde" : "Mitgliedschaften wurden"} ` +
        "entfernt; die Mitglieder kommen ab dem nächsten Login aus dem Schulkonto."
    )
}

/**
 * Ob die Auswahl überhaupt eine Wahl ist.
 *
 * Ohne eigene Gruppen bleibt nur „neu anlegen" — dann wäre ein leeres Auswahlfeld eine
 * Zumutung, und der Satz muss das sagen.
 */
export function hatKandidaten(daten) {
    return (daten?.gruppen ?? []).length > 0
}

/** Der Einleitungssatz über der Liste. */
export function angebotsHinweis(daten) {
    const n = (daten?.angebote ?? []).filter((a) => !a.ignoriert).length
    if (!n) return null
    const was = n === 1 ? "Eine neue Unterrichtsgruppe" : `${n} neue Unterrichtsgruppen`
    return (
        `${was} aus dem Schulkonto ${n === 1 ? "wartet" : "warten"} auf Zuordnung. ` +
        "Angelegt wird nichts von selbst — sonst entstünde neben Ihrer bestehenden " +
        "Gruppe eine zweite."
    )
}

/**
 * Warum sich aus diesem Angebot keine neue Gruppe machen lässt — `null`, wenn es geht.
 *
 * ⚠️ **Ohne Fach entsteht keine Unterrichtsgruppe** (`lege_an` antwortet mit 422). Aus
 * Schülersicht *ist* die Unterrichtsgruppe das Fach; ohne `subject_id` fiele jede
 * fachbezogene Funktion aus, die Gruppe sähe vollständig aus und wäre es nicht.
 *
 * Den Knopf trotzdem anzubieten wäre schlechter als keiner: Er sieht nach einem Weg aus
 * und endet in einer Fehlermeldung. Das **Zuordnen** zu einer vorhandenen Gruppe bleibt
 * möglich — dort kommt das Fach von der Zielgruppe.
 */
export function anlegenGesperrt(angebot) {
    if (angebot?.kann_angelegt_werden !== false) return null
    return "Zu diesem Angebot lässt sich kein Fach bestimmen — ordnen Sie es einer " +
        "vorhandenen Gruppe zu oder legen Sie sie über „Klasse und Fach“ an."
}
