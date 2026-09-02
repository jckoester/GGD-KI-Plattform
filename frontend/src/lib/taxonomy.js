// GENERATED FILE — do not edit manually.
// Source:      backend/app/context/taxonomy.yaml
// Regenerate:  python scripts/generate_taxonomy.py
//              (runs automatically via npm run prebuild / npm run dev)

export const CONTENT_TYPES = {
  "document": [
    "formatierungsvorlage",
    "vokabelliste",
    "quelltext",
    "konvention",
    "methodenblatt",
    "operatorenblatt",
    "praesentation"
  ],
  "knowledge": [
    "fachplan",
    "themengebiet",
    "leitidee",
    "ik_kompetenz",
    "pk_gruppe",
    "pk_kompetenz",
    "leitperspektive",
    "leitperspektive_aspekt",
    "lfdb_baustein",
    "lfdb_themenblock",
    "lfdb_kompetenz",
    "curriculum",
    "kapitel",
    "lernsequenz",
    "methode",
    "sozialform",
    "operator",
    "jahresplan",
    "pruefungsanforderung"
  ],
  "artifact": [
    "unterrichtsstunde",
    "unterrichtseinheit",
    "arbeitsblatt",
    "aufgabe",
    "klausur",
    "code_beispiel",
    "lerntext",
    "lernplan",
    "schuelertext",
    "schuelerpraesentation",
    "strukturierung",
    "feedback_text"
  ],
  "concept": [
    "funktion",
    "bauteil",
    "begriff"
  ]
}

export const SCOPE_ANCHOR_CONTENT_TYPES = new Set([
  "fachplan",
  "themengebiet",
  "leitidee",
  "pk_gruppe",
  "curriculum",
  "kapitel",
  "unterrichtsstunde",
  "unterrichtseinheit"
])

// Importierte Bildungsplan-/Curriculum-Knotentypen — aus der freien /knowledge-Liste
// serverseitig ausgeschlossen (exclude_content_type). Quelle: taxonomy.yaml (C2).
export const BP_CURRICULUM_CONTENT_TYPES = [
  "curriculum",
  "fachplan",
  "leitidee",
  "ik_kompetenz",
  "pk_gruppe",
  "pk_kompetenz",
  "operator",
  "leitperspektive",
  "leitperspektive_aspekt",
  "lfdb_baustein",
  "lfdb_themenblock",
  "lfdb_kompetenz",
  "kapitel",
  "lernsequenz"
]

// Typen mit `ui_status: ruhend` — erscheinen in keiner Auswahl, keinem Filter und
// keiner Such-Facette (ADR-019 F6). Vorhandene Knoten bleiben sicht- und suchbar;
// zum Filtern die Helfer in `knotentypen.js` verwenden, nicht diese Menge direkt.
export const RUHENDE_CONTENT_TYPES = new Set([
  "pruefungsanforderung",
  "lernplan",
  "schuelertext",
  "schuelerpraesentation",
  "strukturierung",
  "feedback_text"
])

export const CATEGORY_LABELS = {
  "document": "Dokument",
  "knowledge": "Wissen",
  "artifact": "Artefakt",
  "concept": "Konzept"
}

export const CATEGORY_COLORS = {
  "document": "bl",
  "knowledge": "gr",
  "artifact": "or",
  "concept": "pu"
}

export const CONTENT_TYPE_LABELS = {
  "formatierungsvorlage": "Formatierungsvorlage",
  "vokabelliste": "Vokabelliste",
  "quelltext": "Quelltext",
  "konvention": "Konvention",
  "methodenblatt": "Methodenblatt",
  "operatorenblatt": "Operatorenblatt",
  "praesentation": "Präsentation",
  "fachplan": "Fachplan",
  "themengebiet": "Themengebiet",
  "leitidee": "Leitidee",
  "ik_kompetenz": "IK-Kompetenz",
  "pk_gruppe": "Prozessbezogene Kompetenzgruppe",
  "pk_kompetenz": "Prozessbezogene Kompetenz",
  "leitperspektive": "Leitperspektive",
  "leitperspektive_aspekt": "Leitperspektive-Aspekt",
  "lfdb_baustein": "LFDB-Baustein",
  "lfdb_themenblock": "LFDB-Themenblock",
  "lfdb_kompetenz": "LFDB-Kompetenz",
  "curriculum": "Schulcurriculum",
  "kapitel": "Kapitel",
  "lernsequenz": "Lernsequenz",
  "methode": "Methode",
  "sozialform": "Sozialform",
  "operator": "Operator",
  "jahresplan": "Jahresplan",
  "pruefungsanforderung": "Prüfungsanforderung",
  "unterrichtsstunde": "Unterrichtsstunde",
  "unterrichtseinheit": "Unterrichtseinheit",
  "arbeitsblatt": "Arbeitsblatt",
  "aufgabe": "Aufgabe",
  "klausur": "Klausur",
  "code_beispiel": "Code-Beispiel",
  "lerntext": "Lerntext",
  "lernplan": "Lernplan",
  "schuelertext": "Schülertext",
  "schuelerpraesentation": "Schülerpräsentation",
  "strukturierung": "Gliederung/Mindmap",
  "feedback_text": "Feedback-Text",
  "funktion": "Funktion",
  "bauteil": "Bauteil",
  "begriff": "Fachbegriff"
}

export const SCOPE_DEFAULTS = {
  "formatierungsvorlage": [
    "school",
    "school"
  ],
  "vokabelliste": [
    "group",
    "private"
  ],
  "quelltext": [
    "group",
    "private"
  ],
  "konvention": [
    "school",
    "subject"
  ],
  "methodenblatt": [
    "school",
    "subject"
  ],
  "operatorenblatt": [
    "school",
    "subject"
  ],
  "praesentation": [
    "group",
    "private"
  ],
  "fachplan": [
    "global",
    "global"
  ],
  "themengebiet": [
    "school",
    "subject"
  ],
  "leitidee": [
    "global",
    "global"
  ],
  "ik_kompetenz": [
    "global",
    "global"
  ],
  "pk_gruppe": [
    "global",
    "global"
  ],
  "pk_kompetenz": [
    "global",
    "global"
  ],
  "leitperspektive": [
    "global",
    "global"
  ],
  "leitperspektive_aspekt": [
    "global",
    "global"
  ],
  "lfdb_baustein": [
    "global",
    "global"
  ],
  "lfdb_themenblock": [
    "global",
    "global"
  ],
  "lfdb_kompetenz": [
    "global",
    "global"
  ],
  "curriculum": [
    "school",
    "subject"
  ],
  "kapitel": [
    "school",
    "subject"
  ],
  "lernsequenz": [
    "school",
    "subject"
  ],
  "methode": [
    "school",
    "subject"
  ],
  "sozialform": [
    "school",
    "school"
  ],
  "operator": [
    "global",
    "global"
  ],
  "jahresplan": [
    "private",
    "private"
  ],
  "pruefungsanforderung": [
    "school",
    "subject"
  ],
  "unterrichtsstunde": [
    "private",
    "private"
  ],
  "unterrichtseinheit": [
    "private",
    "private"
  ],
  "arbeitsblatt": [
    "group",
    "private"
  ],
  "aufgabe": [
    "group",
    "private"
  ],
  "klausur": [
    "private",
    "private"
  ],
  "code_beispiel": [
    "school",
    "private"
  ],
  "lerntext": [
    "school",
    "private"
  ],
  "lernplan": [
    "private",
    "private"
  ],
  "schuelertext": [
    "private",
    "private"
  ],
  "schuelerpraesentation": [
    "private",
    "private"
  ],
  "strukturierung": [
    "private",
    "private"
  ],
  "feedback_text": [
    "private",
    "private"
  ],
  "funktion": [
    "school",
    "subject"
  ],
  "bauteil": [
    "school",
    "subject"
  ],
  "begriff": [
    "school",
    "subject"
  ]
}
