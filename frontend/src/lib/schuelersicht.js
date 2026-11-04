// Reiter „Assistenten" der Gruppenseite (0.32, Päckchen AJ): Beschriftungen und Links.
//
// Die Gründe kommen als Kennungen aus `app/assistants/sichtbarkeit.py` (`GRUENDE`); was dort
// dazukommt, braucht hier einen Text — der Test prüft die Liste.

/** Die Kennungen aus `sichtbarkeit.GRUENDE` — muss mit dem Backend übereinstimmen. */
export const GRUENDE = [
    "entwurf", "in_pruefung", "deaktiviert", "archiviert", "nicht_aktiv",
    "noch_nicht_freigeschaltet", "abgelaufen", "modell", "stufe", "ohne_gruppe",
    "fachschaft", "andere_gruppe", "nur_lehrkraefte", "nur_schueler", "privat", "unbekannt",
];

const TEXTE = {
    entwurf: "Entwurf — noch nicht freigegeben",
    in_pruefung: "wartet auf die Freigabe durch die Administration",
    deaktiviert: "deaktiviert",
    archiviert: "archiviert",
    nicht_aktiv: "nicht aktiv",
    noch_nicht_freigeschaltet: "erst ab dem eingestellten Datum verfügbar",
    abgelaufen: "Verfügbarkeitszeitraum abgelaufen",
    modell: "das Modell ist für diese Klassenstufe nicht freigeschaltet",
    stufe: "für eine andere Klassenstufe",
    ohne_gruppe: "für eine Gruppe freigegeben, aber ohne Gruppe gespeichert",
    fachschaft: "nur für die Lehrkräfte der Fachschaft freigegeben",
    andere_gruppe: "für eine andere Gruppe freigegeben",
    nur_lehrkraefte: "nur für Lehrkräfte",
    nur_schueler: "nur für Schüler:innen",
    privat: "privat — nur für dich",
    unbekannt: "nicht freigegeben",
};

/** „5–7", „ab 11", „bis 6" oder `null` ohne Grenzen. */
export function stufenText({ min_grade: von = null, max_grade: bis = null } = {}) {
    if (von != null && bis != null) return von === bis ? `${von}` : `${von}–${bis}`;
    if (von != null) return `ab ${von}`;
    if (bis != null) return `bis ${bis}`;
    return null;
}

/** Der Grund, lesbar — bei der Klassenstufe mit den Grenzen des Assistenten. */
export function grundText(grund, assistent = {}) {
    const text = TEXTE[grund] ?? TEXTE.unbekannt;
    const stufen = grund === "stufe" ? stufenText(assistent) : null;
    return stufen ? `${text} (Klasse ${stufen})` : text;
}

/** Eigener Assistent → Editor, fremder → Chat mit ihm (Plan F6). */
export function assistentLink(assistent) {
    return assistent.eigen
        ? `/assistants/my/${assistent.id}`
        : `/chat?assistant_id=${assistent.id}`;
}

const QUELLE = {
    festgelegt: "an der Gruppe festgelegt",
    abgeleitet: "aus dem Gruppennamen bzw. den Klassen abgeleitet",
    gewaehlt: "hier gewählt",
};

/** Der Satz über den Jahrgang, nach dem gerechnet wurde. */
export function jahrgangText(sicht) {
    if (sicht?.jahrgang == null) {
        return "Der Jahrgang der Gruppe ist nicht bekannt — Klassenstufen und Modellfreigaben sind deshalb nicht berücksichtigt.";
    }
    const woher = QUELLE[sicht.jahrgang_quelle];
    return `Gerechnet für Klasse ${sicht.jahrgang}${woher ? ` (${woher})` : ""}.`;
}

/** Darf der Reiter den Jahrgang wählen lassen? Nur, wenn die Gruppe keinen hat (Plan F1). */
export function jahrgangWaehlbar(sicht) {
    return sicht?.jahrgang_quelle == null || sicht?.jahrgang_quelle === "gewaehlt";
}

/**
 * Hinweis im Assistenten-Editor (0.32, Plan F3 a): „Freigeben für: Fachschaft" heißt Teilen
 * unter den Lehrkräften des Fachs. Richtet sich der Assistent an Schüler:innen, erreicht er so
 * keine — die Kombination ist erlaubt, liest sich aber wie eine Freigabe für die Klassen.
 *
 * @returns {string|null}
 */
export function fachschaftHinweis({ scope, audience } = {}) {
    if (scope !== "subject_department" || audience === "teacher") return null;
    return "Schüler:innen sehen diesen Assistenten so nicht: Die Fachschaft sind die Lehrkräfte des Fachs. Für eine Klasse gibst du ihn unter „Unterrichtsgruppe“ frei, für alle Schüler:innen unter „Alle Schüler:innen“.";
}
