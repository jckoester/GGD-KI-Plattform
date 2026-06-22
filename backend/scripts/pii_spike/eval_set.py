"""Gelabeltes Eval-Set für den PII-NER-Engine-Spike (Phase 14, Schritt 1).

Realistische deutsche Schüler:innen-/Lehrkraft-Prompts. Jeder Eintrag:
- text:  der Prompt
- gold:  Liste (kategorie, teilstring), die erkannt werden SOLL
         kategorie ∈ {"name", "wohnort"}
- note:  kurze Beschreibung der Schwierigkeit (für die Auswertung)

Trap-/Negativ-Einträge haben gold == [] — ideal ist KEINE Warnung. Jede PER/LOC-
Vorhersage darauf zählt als "Rauschen" (Over-Warning), das die spätere Schwelle
(offene Entscheidung #3) entschärfen muss.

Wiederverwendbar: kann später in die Phase-14-Tests (Schritt 7) übernommen werden.
"""

CASES = [
    # ── Name, Großschreibung (einfach) ──────────────────────────────────────
    {"text": "Ich heiße Lena Hoffmann und brauche Hilfe in Mathe.",
     "gold": [("name", "Lena Hoffmann")], "note": "Vor+Nachname, Großschreibung"},
    {"text": "Mein Name ist Jonas und ich bin in der 8b.",
     "gold": [("name", "Jonas")], "note": "Vorname allein, Großschreibung"},
    {"text": "Kannst du eine Mail an Herrn Schäfer formulieren?",
     "gold": [("name", "Schäfer")], "note": "Nachname mit Anrede"},
    {"text": "Schreib einen Steckbrief über meine Schwester Marie Becker.",
     "gold": [("name", "Marie Becker")], "note": "Vor+Nachname im Satz"},

    # ── Name, Kleinschreibung / informell (HART) ────────────────────────────
    {"text": "mein kumpel tim versteht den dreisatz auch nicht",
     "gold": [("name", "tim")], "note": "kleingeschrieben informell"},
    {"text": "ich bin der jonas aus reutlingen",
     "gold": [("name", "jonas"), ("wohnort", "reutlingen")], "note": "klein, Name+Ort"},
    {"text": "kannst du lena fragen ob sie mir hilft",
     "gold": [("name", "lena")], "note": "kleingeschriebener Vorname"},
    {"text": "ich heiße sophie müller",
     "gold": [("name", "sophie müller")], "note": "klein, Vor+Nachname"},

    # ── Wohnort (Schwerpunkt) ───────────────────────────────────────────────
    {"text": "Ich wohne in der Lindenstraße 4 in Reutlingen.",
     "gold": [("wohnort", "Reutlingen")], "note": "Straße + Stadt"},
    {"text": "Wir ziehen nächsten Monat nach Kornwestheim um.",
     "gold": [("wohnort", "Kornwestheim")], "note": "Stadt im Satz"},
    {"text": "Meine Adresse ist Am Bach 12, 72760 Reutlingen.",
     "gold": [("wohnort", "Reutlingen")], "note": "vollständige Adresse"},
    {"text": "ich komme aus tübingen",
     "gold": [("wohnort", "tübingen")], "note": "kleingeschriebener Ort"},

    # ── Name + Wohnort kombiniert ───────────────────────────────────────────
    {"text": "Mein Name ist Sarah Klein, ich komme aus Tübingen.",
     "gold": [("name", "Sarah Klein"), ("wohnort", "Tübingen")], "note": "beide groß"},
    {"text": "Hallo, ich bin Paul Weber und wohne in Stuttgart-Vaihingen.",
     "gold": [("name", "Paul Weber"), ("wohnort", "Stuttgart-Vaihingen")],
     "note": "Name + Stadtteil"},

    # ── Negativ: kein PII (False-Positive-Disziplin) ────────────────────────
    {"text": "Erklär mir die Photosynthese in einfachen Worten.",
     "gold": [], "note": "kein PII"},
    {"text": "Wie löse ich quadratische Gleichungen mit der pq-Formel?",
     "gold": [], "note": "kein PII"},
    {"text": "Fasse die Französische Revolution in fünf Sätzen zusammen.",
     "gold": [], "note": "kein PII (Thema)"},
    {"text": "Was ist der Unterschied zwischen Akkusativ und Dativ?",
     "gold": [], "note": "kein PII"},
    {"text": "schreib mir ein gedicht über den herbst",
     "gold": [], "note": "kein PII, kleingeschrieben"},

    # ── Trap: Orte/Namen als THEMA, nicht als persönliche Angabe ────────────
    {"text": "Die Hauptstadt von Frankreich ist Paris.",
     "gold": [], "note": "Ort als Faktum (Over-Warning-Falle)"},
    {"text": "Frankfurt am Main ist eine wichtige Finanzstadt.",
     "gold": [], "note": "Ort als Thema, nicht Wohnort"},
    {"text": "Goethe hat den Faust geschrieben.",
     "gold": [], "note": "historischer Name, kein persönliches PII"},
    {"text": "Vergleiche Angela Merkel und Helmut Kohl als Kanzler.",
     "gold": [], "note": "Personen des öffentlichen Lebens (Thema)"},
    {"text": "Im Schwarzwald gibt es viele Wanderwege.",
     "gold": [], "note": "Region als Thema"},
    {"text": "Erkläre den Wasserkreislauf am Beispiel des Rheins.",
     "gold": [], "note": "Fluss als Thema"},

    # ── Schwierige Mischfälle ───────────────────────────────────────────────
    {"text": "Meine Lehrerin Frau Dr. Bauer hat gesagt, ich soll üben.",
     "gold": [("name", "Bauer")], "note": "Titel + Nachname"},
    {"text": "Kann Max heute zu mir nach Esslingen kommen?",
     "gold": [("name", "Max"), ("wohnort", "Esslingen")], "note": "Name + Ort, Frage"},
    {"text": "ich wohne bei meiner oma in der nähe von ulm",
     "gold": [("wohnort", "ulm")], "note": "Ort klein, vager Kontext"},
    {"text": "Schreibe eine Bewerbung für Lisa Schneider, wohnhaft in Heilbronn.",
     "gold": [("name", "Lisa Schneider"), ("wohnort", "Heilbronn")],
     "note": "Bewerbungskontext, beide PII"},
    {"text": "Mein Bruder Ben geht in die Grundschule.",
     "gold": [("name", "Ben")], "note": "kurzer Vorname (3 Buchst.)"},
]
