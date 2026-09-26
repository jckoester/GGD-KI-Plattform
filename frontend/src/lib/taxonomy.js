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
    "begriff",
    "stoffsteckbrief"
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
  "feedback_text"
])

// Typen, deren `valid_until` beim Anlegen aufs Schuljahresende vorbelegt wird
// (`before_insert`-Regel in app/db/models.py). Das Formular sagt das dazu — ein
// leeres Feld heißt hier nicht „läuft nie ab".
export const SCHULJAHRESENDE_CONTENT_TYPES = new Set([
  "unterrichtsstunde",
  "unterrichtseinheit",
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
    "beschreibung": "Handreichungen für Schüler:innen zu einem fachlichen Verfahren — was zu tun ist und worauf es ankommt. Die Fachschaft pflegt sie.",
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
    "schueler": true,
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
    "schueler": true,
    "content": {
      "label": "Inhalt des Blattes",
      "pflicht": false
    }
  },
  "methode": {
    "beschreibung": "Didaktische Arrangements für den Unterricht — Placemat, Galeriegang, Think-Pair-Share. Nicht gemeint sind fachliche Verfahren wie die Gedichtanalyse; die erklärt ein Methodenblatt. Fachübergreifende Einträge pflegt die Administration, fachspezifische die jeweilige Fachschaft.",
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
    "sidebar": true,
    "relationen": {
      "related_to": {
        "label": "steht in Beziehung zu",
        "ziel": [
          "methode"
        ]
      }
    },
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
    "sidebar": true,
    "content": {
      "label": "Kurzbeschreibung",
      "pflicht": false
    }
  },
  "begriff": {
    "beschreibung": "Fachbegriffe mit Definition. Gleichnamige Begriffe je Fach sind der Normalfall — „Energie\" heißt in Physik etwas anderes als in Ethik.",
    "spalten": [
      "titel",
      "fassung",
      "fach",
      "ab_klasse",
      "pruefstatus",
      "status",
      "geaendert"
    ],
    "filter": [
      "fach",
      "ab_klasse",
      "pruefstatus",
      "status",
      "titel"
    ],
    "sidebar": true,
    "schueler": true,
    "relationen": {
      "related_to": {
        "label": "steht in Beziehung zu",
        "ziel": [
          "begriff"
        ]
      },
      "part_of": {
        "label": "gehört zum Themengebiet",
        "ziel": [
          "themengebiet"
        ]
      },
      "references": {
        "label": "wird im Bildungsplan verlangt in",
        "ziel": [
          "ik_kompetenz"
        ]
      },
      "requires": {
        "label": "setzt voraus",
        "ziel": [
          "begriff"
        ]
      },
      "is_a": {
        "label": "ist ein(e)",
        "ziel": [
          "begriff"
        ]
      }
    },
    "content": {
      "label": "Definition",
      "pflicht": true,
      "hinweis": "Macht den Eintrag thematisch auffindbar — auch für Suchende, die den Begriff nicht kennen."
    }
  },
  "stoffsteckbrief": {
    "beschreibung": "Stoffe mit Formel, Eigenschaften und Gefahrenhinweisen. Reinstoff und Lösung sind getrennt (Chlorwasserstoff / Salzsäure) — sonst verwischt die Unterscheidung zwischen Säure und saurer Lösung.",
    "spalten": [
      "titel",
      "formel",
      "fach",
      "pruefstatus",
      "status",
      "geaendert"
    ],
    "filter": [
      "fach",
      "pruefstatus",
      "status",
      "titel"
    ],
    "sidebar": true,
    "schueler": true,
    "relationen": {
      "is_a": {
        "label": "gehört zur Stoffklasse",
        "ziel": [
          "begriff"
        ]
      },
      "related_to": {
        "label": "steht in Beziehung zu",
        "ziel": [
          "begriff",
          "stoffsteckbrief"
        ]
      },
      "references": {
        "label": "wird im Bildungsplan verlangt in",
        "ziel": [
          "ik_kompetenz"
        ]
      }
    },
    "content": {
      "label": "Definition",
      "pflicht": true,
      "hinweis": "Was für ein Stoff das ist, in einem Satz. Darunter Erklärung und Beispiele."
    }
  }
}

// Metadaten-Feldschema je Typ — dieselbe Beschreibung, aus der das Backend prüft
// (app/context/metadata.py). Der Editor baut sein Formular daraus.
export const FELD_SCHEMATA = {
  "kapitel": {
    "std": {
      "typ": "int",
      "min": 0,
      "label": "Stunden (Soll)",
      "hinweis": "Wie viele Unterrichtsstunden das Kapitel vorsieht. Grundlage der Stundenbilanz im Jahresplan."
    },
    "reihenfolge": {
      "typ": "int",
      "min": 0,
      "label": "Reihenfolge",
      "hinweis": "Position im Curriculum — kleinere Zahl steht weiter vorn."
    },
    "einleitung": {
      "typ": "text",
      "label": "Einleitung",
      "hinweis": "Der einleitende Text des Kapitels aus dem Bildungsplan."
    },
    "breadcrumb": {
      "typ": "text",
      "label": "Pfad im Bildungsplan",
      "hinweis": "Der Weg zum Kapitel, etwa „Chemie › Klasse 9/10 › Stoffe und ihre Eigenschaften\". Fließt in das Embedding ein."
    }
  },
  "methode": {
    "ablauf": {
      "typ": "text",
      "label": "Ablauf in einem Satz",
      "hinweis": "Woran man die Methode erkennt, ohne ihren Namen zu kennen — nur der Ablauf, keine Hinweise zum Einsatz. Dieser Satz allein entscheidet darüber, ob die Methode thematisch gefunden wird. Ohne ihn zählt die Kurzbeschreibung."
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
      "hinweis": "Nur ausfüllen, wenn es diesen Begriff in mehreren Fassungen gibt: „Energie\" in Klasse 6 verlangt eine andere Definition als in Klasse 11, „Oxidation\" in Klasse 8 eine andere als in Klasse 10. Zwei Einträge mit verschiedener Stufe sind der vorgesehene Weg dahin."
    },
    "fassung": {
      "typ": "text",
      "label": "Fassung",
      "hinweis": "Unterscheidet gleichnamige Einträge in der Liste — „Sauerstoffaufnahme\" gegenüber „Elektronenabgabe\". Ohne sie stünde derselbe Titel zweimal da."
    },
    "bevorzugter_begriff": {
      "typ": "text",
      "label": "Bevorzugte Bezeichnung",
      "hinweis": "Die an dieser Schule übliche Bezeichnung. Der Assistent antwortet damit, auch wenn gefragt wurde: „Atombindung\" beantwortet er als „Elektronenpaarbindung\"."
    },
    "genus": {
      "typ": "auswahl",
      "label": "Artikel",
      "werte": [
        "der",
        "die",
        "das"
      ],
      "hinweis": "Für Lernende, die Deutsch als Zweitsprache sprechen — und für Antworten, die den Begriff im Satz beugen."
    },
    "plural": {
      "typ": "text",
      "label": "Mehrzahl",
      "hinweis": "Ersetzt Plural-Aliase; die Suche findet beide Formen ohnehin."
    },
    "fehlvorstellungen": {
      "typ": "liste",
      "label": "Häufige Irrtümer",
      "hinweis": "Typische Fehlvorstellungen, gegen die eine Erklärung anarbeiten muss („Beim Sieden zerfällt Wasser in Wasserstoff und Sauerstoff\"). Der Assistent bekommt sie mit und kann sie ansprechen."
    },
    "pruefstatus": {
      "typ": "auswahl",
      "label": "Prüfstatus",
      "werte": [
        "entwurf",
        "fachlich_geprueft",
        "freigegeben"
      ],
      "hinweis": "Wie weit der Eintrag fachlich geprüft ist. Vorbereitung für die Frage, ob Schüler:innen Entwürfe sehen — heute rein informativ."
    },
    "quelle": {
      "typ": "text",
      "label": "Herkunft",
      "hinweis": "Woher der Entwurf stammt — Lehrwerk, Fachschaft, eigene Arbeit."
    }
  },
  "stoffsteckbrief": {
    "formel": {
      "typ": "text",
      "label": "Formel",
      "hinweis": "In mhchem-Schreibweise, etwa `\\ce{H2O}`. Bei Lösungen die Kurzform (`HCl(aq)`)."
    },
    "smiles": {
      "typ": "text",
      "label": "SMILES",
      "hinweis": "Nur für Reinstoffe; bei Gemischen leer lassen."
    },
    "trivialnamen": {
      "typ": "liste",
      "label": "Alltagsnamen",
      "hinweis": "Kochsalz, Trockeneis, gebrannte Magnesia. Auch fachlich schiefe Namen wie „Kohlensäure\" gehören hierher — die Richtigstellung steht im Text. Geht in die Suche ein: Danach fragen Schüler:innen."
    },
    "nachweis": {
      "typ": "text",
      "label": "Nachweis",
      "hinweis": "Die Nachweisreaktion in einem Satz. Leer, wenn der Bildungsplan keine verlangt."
    },
    "bevorzugter_begriff": {
      "typ": "text",
      "label": "Bevorzugte Bezeichnung",
      "hinweis": "Die an dieser Schule übliche Bezeichnung."
    },
    "genus": {
      "typ": "auswahl",
      "label": "Artikel",
      "werte": [
        "der",
        "die",
        "das"
      ],
      "hinweis": "Für Lernende mit Deutsch als Zweitsprache."
    },
    "plural": {
      "typ": "text",
      "label": "Mehrzahl",
      "hinweis": "Ein Gedankenstrich, wo es keine gibt."
    },
    "pruefstatus": {
      "typ": "auswahl",
      "label": "Prüfstatus",
      "werte": [
        "entwurf",
        "fachlich_geprueft",
        "freigegeben"
      ],
      "hinweis": "Gefahrstoffangaben ändern sich; der Status sagt, wann zuletzt jemand fachlich daraufgesehen hat."
    },
    "quelle": {
      "typ": "text",
      "label": "Herkunft",
      "hinweis": "Woher die Angaben stammen — bei Gefahrstoffdaten mit dem Datum des DEGINTU-Abgleichs."
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
  "methode": "Unterrichtsmethode",
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
  "begriff": "Fachbegriff",
  "stoffsteckbrief": "Stoffsteckbrief"
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
    "group_teachers",
    "group_teachers"
  ],
  "pruefungsanforderung": [
    "school",
    "subject"
  ],
  "unterrichtsstunde": [
    "group_teachers",
    "group_teachers"
  ],
  "unterrichtseinheit": [
    "group_teachers",
    "group_teachers"
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
  ],
  "stoffsteckbrief": [
    "school",
    "subject"
  ]
}
