// GENERATED FILE — do not edit manually.
// Source:      config/taxonomy.yaml
// Regenerate:  python scripts/generate_taxonomy.py
//              (runs automatically via npm run prebuild / npm run dev)

export const CONTENT_TYPES = {
  "document": [
    "formatierungsvorlage",
    "vokabelliste",
    "aufgabenblatt",
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
    "curriculum",
    "unterrichtseinheit",
    "methode",
    "operator_didaktisch",
    "jahresplan",
    "pruefungsanforderung"
  ],
  "artifact": [
    "unterrichtsentwurf",
    "unterrichtsstunde",
    "reflexion",
    "arbeitsblatt",
    "aufgabe",
    "klausur",
    "code_beispiel",
    "lerntext",
    "gliederung",
    "mindmap",
    "lernplan",
    "schuelertext",
    "feedback_text"
  ],
  "concept": [
    "funktion",
    "bauteil",
    "operator_math",
    "abstrakt"
  ]
}

export const SCOPE_ANCHOR_CONTENT_TYPES = new Set([
  "fachplan",
  "themengebiet",
  "leitidee",
  "pk_gruppe",
  "curriculum",
  "unterrichtseinheit",
  "unterrichtsstunde"
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
  "aufgabenblatt": "Aufgabenblatt",
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
  "curriculum": "Schulcurriculum",
  "unterrichtseinheit": "Unterrichtseinheit",
  "methode": "Methode",
  "operator_didaktisch": "Didaktischer Operator",
  "jahresplan": "Jahresplan",
  "pruefungsanforderung": "Prüfungsanforderung",
  "unterrichtsentwurf": "Unterrichtsentwurf",
  "unterrichtsstunde": "Unterrichtsstunde",
  "reflexion": "Reflexion",
  "arbeitsblatt": "Arbeitsblatt",
  "aufgabe": "Aufgabe",
  "klausur": "Klausur",
  "code_beispiel": "Code-Beispiel",
  "lerntext": "Lerntext",
  "gliederung": "Gliederung",
  "mindmap": "Mindmap",
  "lernplan": "Lernplan",
  "schuelertext": "Schülertext",
  "feedback_text": "Feedback-Text",
  "funktion": "Funktion",
  "bauteil": "Bauteil",
  "operator_math": "Mathematischer Operator",
  "abstrakt": "Abstraktes Konzept"
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
  "aufgabenblatt": [
    "group",
    "private"
  ],
  "quelltext": [
    "group",
    "private"
  ],
  "konvention": [
    "school",
    "school"
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
    "school",
    "subject"
  ],
  "fachplan": [
    "global",
    "global"
  ],
  "themengebiet": [
    "school",
    "school"
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
  "curriculum": [
    "school",
    "subject"
  ],
  "unterrichtseinheit": [
    "school",
    "subject"
  ],
  "methode": [
    "school",
    "subject"
  ],
  "operator_didaktisch": [
    "school",
    "subject"
  ],
  "jahresplan": [
    "private",
    "private"
  ],
  "pruefungsanforderung": [
    "school",
    "school"
  ],
  "unterrichtsentwurf": [
    "private",
    "private"
  ],
  "unterrichtsstunde": [
    "private",
    "private"
  ],
  "reflexion": [
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
  "gliederung": [
    "private",
    "private"
  ],
  "mindmap": [
    "private",
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
  "feedback_text": [
    "private",
    "private"
  ],
  "funktion": [
    "school",
    "school"
  ],
  "bauteil": [
    "school",
    "school"
  ],
  "operator_math": [
    "school",
    "school"
  ],
  "abstrakt": [
    "school",
    "school"
  ]
}
