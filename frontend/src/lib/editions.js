/**
 * Editionsbewusstes Laden der Kompetenz-Auswahl (IK/PK).
 *
 * Ein Fach kann mehrere Bildungsplan-Editionen gleichzeitig aktiv haben — das ist kein
 * Fehlzustand, sondern der Normalfall während eines Editionswechsels: Der Fahrplan in
 * `subjects.yaml` weist verschiedenen Klassenstufen verschiedene Fassungen zu, und beide
 * Knotenbestände stehen nebeneinander in der Datenbank.
 *
 * Wer ohne `bp_version` sucht, bekommt dann **beide** Fassungen — bei den prozessbezogenen
 * Kompetenzen besonders sichtbar, weil die keine Klassenstufe tragen und deshalb auch der
 * Stufenfilter sie nicht trennt: gleiche Nummer, anderer Text, doppelt in der Liste.
 *
 * Die Edition kommt aus einer von zwei Quellen:
 *
 *   1. **explizit** — ein Curriculum ist an seine Edition gebunden (`metadata.bp_version`,
 *      seit 0.5.0 unveränderlich, weil alle Kompetenzverweise daran hängen). Sie steht
 *      sofort fest.
 *   2. **aufgelöst** — sonst aus (Fach, Stufe, Schuljahr) über
 *      `/context/subjects/{id}/active-bp-version`. Das ist ein Netzabruf und damit
 *      **nicht** sofort da.
 *
 * Im zweiten Fall darf nicht schon geladen werden, solange die Antwort aussteht. Genau das
 * war der Fehler: Der erste Ladevorgang lief ungefiltert los, der zweite gefiltert
 * hinterher — und welche der beiden Antworten zuletzt ankam, entschied darüber, ob die
 * Liste doppelte Einträge zeigte.
 */

/**
 * Entscheidet, ob geladen werden darf und mit welchem Editionsfilter.
 *
 * @param {object} o
 * @param {number|null} o.subjectId  Fach; ohne Fach gibt es nichts zu laden
 * @param {string|null} o.bpVersion  explizit vorgegebene Edition (Quelle 1)
 * @param {number|null} o.grade      Klassenstufe für die Auflösung (Quelle 2)
 * @param {string|null|undefined} o.resolved  Ergebnis der Auflösung;
 *        `undefined` = steht noch aus, `null` = Fach hat keine versionierten Knoten
 * @returns {{load: boolean, bpFilter: string|null}}
 */
export function editionLoadPlan({
    subjectId = null,
    bpVersion = null,
    grade = null,
    resolved = undefined,
} = {}) {
    if (!subjectId) return { load: false, bpFilter: null }

    // Quelle 1: steht fest, kein Warten nötig.
    if (bpVersion) return { load: true, bpFilter: bpVersion }

    // Ohne Stufe gibt es nichts aufzulösen — ungefiltert ist hier das Beste, was geht.
    if (!grade) return { load: true, bpFilter: null }

    // Quelle 2: Auflösung läuft noch. Warten statt ungefiltert vorpreschen.
    if (resolved === undefined) return { load: false, bpFilter: null }

    return { load: true, bpFilter: resolved }
}
