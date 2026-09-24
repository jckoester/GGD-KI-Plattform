/**
 * Persönlicher Ausfall in der Jahresplanung (Paket 5, AP4).
 *
 * ⚠️ **Die Mechanik markiert und schlägt vor — sie handelt nicht** (Jan, 24.09.2026):
 * „Je nach Unterrichtsgruppe werden die Auswirkungen eines Ausfalls sehr unterschiedlich
 * sein … Das ist aktive Arbeit der Lehrkraft." Was hier steht, ist deshalb Beschriftung
 * und Warnung — die Folgen entscheidet die Lehrkraft (AP5).
 */

const HERKUNFT_TEXT = {
    stundenplan: "aus dem Stundenplan",
    eigen: "selbst eingetragen",
    assistent: "vom Assistenten eingetragen",
}

/**
 * Woher der Ausfall dieser Stunde stammt — `null`, wenn sie nicht ausfällt.
 *
 * ⚠️ **Die Kategorie wird mitgeprüft.** `ausfall_herkunft` bleibt stehen, wenn eine
 * Stunde die Kategorie über einen Weg verlässt, der die Felder nicht mitführt — den
 * Snapshot-Restore etwa, der aus einem JSON ohne diese Spalten schreibt. Ohne die
 * Prüfung meldete die Zeile einen Ausfall, den es nicht mehr gibt.
 */
export function herkunftText(slot) {
    if (slot?.kategorie !== "ausfall") return null
    return HERKUNFT_TEXT[slot?.ausfall_herkunft] ?? null
}

/** Ob die Lehrkraft diesen Ausfall selbst zurücknehmen kann. */
export function darfZurueckgenommenWerden(slot) {
    return slot?.kategorie === "ausfall" && slot?.ausfall_herkunft === "eigen"
}

/**
 * Der Satz vor dem Zurücknehmen eines ganzen Tages.
 *
 * ⚠️ **Er muss vorher stehen, nicht hinterher** (entschieden 24.09.2026, F4). Nach dem
 * Schreiben ist nicht mehr unterscheidbar, ob ein Slot über „ganzer Tag" oder einzeln
 * markiert wurde — beide tragen `herkunft = 'eigen'`. Das Zurücknehmen nimmt deshalb
 * beides mit. Hinnehmbar, solange es angekündigt ist; eine stille Rücknahme wäre es
 * nicht.
 */
export function ruecknahmeWarnung(reichweite) {
    if (reichweite !== "tag") return null
    return "Das nimmt alle selbst eingetragenen Ausfälle dieses Tages zurück — auch "
        + "solche, die Sie einzeln für eine Stunde gesetzt haben. Ausfälle aus dem "
        + "Stundenplan bleiben."
}

/** Die Frage vor dem Eintragen — sie nennt die Reichweite beim Namen. */
export function eintragFrage(reichweite, gruppenname) {
    return reichweite === "tag"
        ? "Alle Ihre Stunden dieses Tages als Ausfall markieren?"
        : `Alle Stunden von ${gruppenname || "dieser Gruppe"} an diesem Tag als Ausfall markieren?`
}
