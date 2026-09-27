/**
 * Texte und Regeln rund um den Beitrittscode (AP4).
 *
 * Die Logik steht hier und nicht in der Komponente: Das Projekt hat keine
 * Svelte-Komponententests, und gerade die Rücknahme-Texte müssen stimmen — sie sind
 * das Letzte, was eine Lehrkraft liest, bevor sie Mitgliedschaften löscht.
 */

/** Wie der Code dasteht: gültig, abgelaufen oder gar nicht vorhanden. */
export function codeLage(antwort) {
    if (!antwort?.code) return "keiner"
    return antwort.gueltig ? "gueltig" : "abgelaufen"
}

/**
 * Der Satz unter dem Code.
 *
 * „Abgelaufen" ist eine eigene Lage und **nicht** dasselbe wie „kein Code": Im einen
 * Fall erneuert man, im anderen gibt man erstmals aus. Wer beides gleich benennt,
 * lässt die Lehrkraft rätseln, warum niemand beitreten kann.
 */
export function codeHinweis(antwort) {
    switch (codeLage(antwort)) {
        case "keiner":
            return "Noch kein Code ausgegeben. Schüler:innen können dieser Gruppe nicht selbst beitreten."
        case "abgelaufen":
            return "Der Code ist abgelaufen. Ein neuer gilt wieder drei Tage."
        default:
            return `Gültig bis ${alsDatum(antwort.gueltig_bis)}. Im Unterricht vorlesen oder anschreiben.`
    }
}

/** Die Beitritte je Tag, absteigend — der jüngste zuerst, denn der ist der verdächtige. */
export function beitritteAbsteigend(antwort) {
    return [...(antwort?.beitritte ?? [])].sort((a, b) => b.tag.localeCompare(a.tag))
}

/** Wie viele insgesamt über diesen Code beigetreten sind. */
export function beitritteGesamt(antwort) {
    return (antwort?.beitritte ?? []).reduce((n, b) => n + b.anzahl, 0)
}

/**
 * Die Rückfrage vor einer Rücknahme — mit Zahl **und** Folge.
 *
 * ⚠️ Die Folge gehört in den Satz: Der Code wird dabei ungültig, und die Richtigen
 * müssen erneut beitreten. Ohne diesen Hinweis wirkt die Rücknahme wie ein
 * Aufräumen — und die Lehrkraft steht danach vor einer Klasse, die nicht mehr
 * hineinkommt.
 */
export function ruecknahmeFrage(anzahl, tag = null) {
    const was = anzahl === 1 ? "1 Beitritt wird" : `${anzahl} Beitritte werden`
    const wann = tag ? ` vom ${alsDatum(tag)}` : ""
    return (
        `${was}${wann} zurückgenommen.\n\n` +
        "Der Code wird dabei ungültig. Wer zu Recht beigetreten ist, muss mit einem " +
        "neuen Code erneut beitreten.\n\nFortfahren?"
    )
}

/** Die Antwort auf einen Beitrittsversuch — für Schüler:innen lesbar. */
export function beitrittFehler(nachricht) {
    const text = (nachricht ?? "").toLowerCase()
    if (text.includes("abgelaufen")) {
        return "Dieser Code ist abgelaufen. Bitte die Lehrkraft um einen neuen."
    }
    if (text.includes("schüler")) {
        return "Beitrittscodes sind für Schüler:innen."
    }
    return "Dieser Code gilt nicht. Bitte die Schreibweise prüfen."
}

function alsDatum(wert) {
    if (!wert) return ""
    const d = new Date(wert)
    return Number.isNaN(d.getTime())
        ? String(wert)
        : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" })
}
