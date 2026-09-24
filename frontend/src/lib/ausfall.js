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

/**
 * Die drei Wege nach einem Ausfall — `null`, wenn es nichts zu entscheiden gibt.
 *
 * ⚠️ **Keiner davon geschieht automatisch** (Jan, 24.09.2026): „Je nach
 * Unterrichtsgruppe werden die Auswirkungen eines Ausfalls sehr unterschiedlich sein …
 * Das ist aktive Arbeit der Lehrkraft." Welcher richtig ist, hängt am Fach, an der
 * Einheit und am Rest des Halbjahres — das weiß nur sie.
 *
 * Bei `mitInhalt === 0` gibt es **keine** Frage: Eine leere Stunde fällt aus, und damit
 * ist es gut. Danach zu fragen hieße, nach Arbeit zu rufen, die niemand hat.
 */
export function ausfallWege(ergebnis) {
    const mit = ergebnis?.mit_inhalt ?? 0
    if (!mit) return null
    return {
        anzahl: mit,
        satz: mit === 1
            ? "Eine ausgefallene Stunde hatte geplante Inhalte. Was soll damit geschehen?"
            : `${mit} ausgefallene Stunden hatten geplante Inhalte. Was soll damit geschehen?`,
        wege: [
            {
                id: "entfallen",
                text: "Inhalte entfallen",
                hinweis: "Die Einheit rückt nicht nach — der Stoff ist gestrichen.",
            },
            {
                id: "verschieben",
                text: "Stunden verschieben",
                hinweis: "Die Inhalte wandern auf die folgenden Stunden.",
            },
            {
                id: "umplanen",
                text: "Umplanen",
                hinweis: "Die Einheit neu zuschneiden — kürzen oder zusammenlegen.",
            },
        ],
    }
}

/**
 * Der Satz, mit dem der Assistent den Fall übernimmt.
 *
 * Zwei Absichten, zwei Sätze: **verschieben** rückt den Stoff nach hinten,
 * **umplanen** stellt die Einheit selbst in Frage. Sie in einen Satz zu legen hieße,
 * dem Modell die Entscheidung zu überlassen, die gerade die Lehrkraft getroffen hat.
 */
export function assistentFrage(weg, datumIso) {
    const [y, m, d] = (datumIso || "").split("-")
    const datum = y ? `${+d}.${+m}.${y}` : "diesem Tag"
    if (weg === "verschieben") {
        // ⚠️ **„Inhalte" allein genügte nicht.** Am 24.09.2026 kam am Zieltermin nur das
        // Thema an — das Modell hatte `set_topic` gewählt statt `move_content`. Der Satz
        // nennt jetzt, was mitkommen soll; die Werkzeugbeschreibung sagt, womit.
        return `Am ${datum} sind geplante Stunden ausgefallen. Bitte verschiebe die `
            + "geplanten Stunden vollständig auf die folgenden Termine — mit "
            + "Unterrichtseinheit und Stundenentwurf, nicht nur dem Thema."
    }
    return `Am ${datum} sind geplante Stunden ausgefallen. Bitte schlage vor, wie ich die `
        + "betroffene Unterrichtseinheit kürzen oder umverteilen kann."
}

/**
 * Ob an dieser **einen** Zeile noch etwas zu entscheiden ist.
 *
 * ⚠️ **Am Slot, nicht über der Tabelle** (Jan, 24.09.2026): „der Hinweis zum
 * Verschiebe-Assistenten erscheint nur oberhalb der Jahresplanungstabelle, nicht am
 * Ausfallslot, wo ich ihn erwartet hätte."
 *
 * Das ist mehr als eine Platzfrage. Ein Banner über der Tabelle ist **Sitzungszustand**:
 * Es verschwindet beim Neuladen, und die offene Entscheidung wird unsichtbar, obwohl sie
 * offen bleibt. Diese Bedingung liest die **Daten** — sie steht wieder da, solange sie
 * gilt, und sie steht dort, wo die betroffene Stunde ist.
 *
 * `anpassung_noetig` ist der Schalter: Das Eintragen setzt ihn, „Inhalte entfallen"
 * räumt ihn ab. Ohne ihn bliebe der Hinweis auch nach der Entscheidung stehen.
 */
export function zeileBrauchtEntscheidung(slot) {
    if (slot?.kategorie !== "ausfall") return false
    if (!slot?.anpassung_noetig) return false
    return !!(slot.ue_node_id || slot.stunde_node_id || (slot.thema || "").trim())
}
