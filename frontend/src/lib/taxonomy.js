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

// Typen mit gepflegter Sammlungsansicht (/knowledge/collections/<typ>).
// Beschreibung, Spalten, Filter und Content-Label je Typ; Reihenfolge = YAML.
export const COLLECTIONS = {
  "methodenblatt": {
    "beschreibung": "Handreichungen für Schüler:innen zu einer Methode — was zu tun ist und worauf es ankommt. Die Fachschaft pflegt sie.",
    "spalten": [
      "titel",
      "fach",
      "status",
      "geaendert"
    ],
    "filter": [
      "fach",
      "status",
      "titel"
    ],
    "content": {
      "label": "Inhalt des Blattes",
      "pflicht": false
    }
  },
  "operatorenblatt": {
    "beschreibung": "Erklärungen zu den Operatoren eines Fachs — was „nennen\", „erläutern\" oder „beurteilen\" dort konkret verlangt.",
    "spalten": [
      "titel",
      "fach",
      "status",
      "geaendert"
    ],
    "filter": [
      "fach",
      "status",
      "titel"
    ],
    "content": {
      "label": "Inhalt des Blattes",
      "pflicht": false
    }
  },
  "methode": {
    "beschreibung": "Unterrichtsmethoden mit Kurzbeschreibung. Fachübergreifende Einträge pflegt die Administration, fachspezifische die jeweilige Fachschaft.",
    "spalten": [
      "titel",
      "fach",
      "aliase",
      "status",
      "geaendert"
    ],
    "filter": [
      "fach",
      "status",
      "titel"
    ],
    "content": {
      "label": "Kurzbeschreibung",
      "pflicht": true,
      "hinweis": "Macht den Eintrag thematisch auffindbar — auch für Suchende, die den Namen nicht kennen."
    }
  },
  "sozialform": {
    "beschreibung": "In welcher Form gearbeitet wird — Einzel-, Partner-, Gruppenarbeit und dergleichen. Eine kleine, schulweit gepflegte Menge; kein Fachbezug.",
    "spalten": [
      "titel",
      "aliase",
      "status",
      "geaendert"
    ],
    "filter": [
      "status",
      "titel"
    ],
    "content": {
      "label": "Kurzbeschreibung",
      "pflicht": false
    }
  },
  "begriff": {
    "beschreibung": "Fachbegriffe mit Definition. Gleichnamige Begriffe je Fach sind der Normalfall — „Energie\" heißt in Physik etwas anderes als in Ethik.",
    "spalten": [
      "titel",
      "fach",
      "ab_klasse",
      "status",
      "geaendert"
    ],
    "filter": [
      "fach",
      "ab_klasse",
      "status",
      "titel"
    ],
    "content": {
      "label": "Definition",
      "pflicht": true,
      "hinweis": "Macht den Eintrag thematisch auffindbar — auch für Suchende, die den Begriff nicht kennen."
    }
  }
}

// Metadaten-Feldschema je Typ — dieselbe Beschreibung, aus der das Backend prüft
// (app/context/metadata.py). Der Editor baut sein Formular daraus.
export const FELD_SCHEMATA = {
  "methode": {
    "aliase": {
      "typ": "liste",
      "label": "Andere Bezeichnungen",
      "hinweis": "z. B. „Think-Pair-Share“ für „Denken – Austauschen – Vorstellen“"
    }
  },
  "sozialform": {
    "aliase": {
      "typ": "liste",
      "label": "Andere Bezeichnungen"
    }
  },
  "strukturierung": {
    "form": {
      "typ": "auswahl",
      "label": "Form",
      "werte": [
        "gliederung",
        "mindmap"
      ],
      "hinweis": "Löst die früheren Einzeltypen `gliederung` und `mindmap` ab (V2)"
    }
  },
  "begriff": {
    "ab_klasse": {
      "typ": "int",
      "label": "Ab Klassenstufe",
      "min": 1,
      "max": 13,
      "hinweis": "Für welche Stufe diese Fassung gemeint ist. „Energie\" in Klasse 6 verlangt eine andere Definition als in Klasse 11; zwei Einträge mit verschiedener Stufe sind der vorgesehene Weg dahin."
    }
  }
}

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
