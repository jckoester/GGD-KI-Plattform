/**
 * Warum an dieser Gruppe kein Curriculum-Kapitel zur Auswahl steht.
 *
 * ⚠️ **Drei Lagen sahen bis zum 24.09.2026 gleich aus** — eine leere Liste, und darunter
 * der Satz „Kein Curriculum für diese Gruppe gefunden". Nur in **einem** der drei Fälle
 * stimmte er; in den beiden anderen schickte er die Lehrkraft auf die falsche Suche:
 *
 * | Lage | Was wirklich fehlt | Was zu tun ist |
 * |---|---|---|
 * | `fach_fehlt` | das **Fach** an der Gruppe | Gruppe mit Fach neu anlegen oder zuordnen |
 * | `stufe_unbekannt` | der **Jahrgang** | Jahrgang an der Gruppe setzen |
 * | `kein_curriculum` | tatsächlich das Curriculum | nichts — die Verknüpfung ist optional |
 *
 * Der Befund kam aus dem Betrieb: In Chemie meldete die Jahresplanung „kein Curriculum",
 * während in Wahrheit einmal das Fach an der Gruppe fehlte (`ch-ks-abi28`) und einmal der
 * Jahrgang nicht ableitbar war (`ch-tl-abi28`).
 */

/**
 * @param {{curricula?: Array, grade_unbekannt?: boolean, fach_fehlt?: boolean}} daten
 * @returns {{art: string, text: string, tun: string|null}|null} `null`, wenn alles passt.
 */
export function curriculumLage(daten) {
    const hatKapitel = (daten?.curricula ?? []).some((c) => (c.kapitel ?? []).length > 0)
    if (hatKapitel) return null

    if (daten?.fach_fehlt) {
        return {
            art: "fach_fehlt",
            text: "Dieser Gruppe ist kein Fach zugeordnet.",
            tun: "Ohne Fach gibt es kein Curriculum, keine Assistentenauswahl und keine "
                + "Fachseite. Legen Sie die Gruppe über „Klasse und Fach“ neu an.",
        }
    }
    if (daten?.grade_unbekannt) {
        return {
            art: "stufe_unbekannt",
            text: "Der Jahrgang dieser Gruppe ist nicht bekannt.",
            // ⚠️ Früher stand hier „es werden alle Curricula des Fachs angezeigt“ — das
            // war die Beschreibung eines Fehlers: Einem Abi-Kurs wurde „CH Kl. 8“
            // angeboten. Jetzt wird nichts angeboten, und der Satz sagt, warum.
            tun: "Tragen Sie ihn unter „Meine Unterrichtsgruppen“ ein, dann erscheinen "
                + "die passenden Kapitel.",
        }
    }
    return {
        art: "kein_curriculum",
        text: "Für diese Stufe ist kein Curriculum hinterlegt.",
        tun: null,
    }
}
