"""Datensparsamkeit: Erkennung personenbezogener Eingaben (Phase 14).

Server-seitiger Scan auf **Name** + **Wohnort** via spaCy-NER (`de_core_news_md`) +
case-unabhängige Cue-Patterns + Themen-Schwelle (Engine-Entscheidung: siehe
``backend/scripts/pii_spike/DECISION.md``). Kein Persistieren, kein externer Call —
der Scan läuft im vertrauenswürdigen Backend, bevor etwas an den Provider geht.

Strukturierte PII (E-Mail/Telefon/IBAN) wird bewusst **client-seitig** geprüft (D-C);
dieses Modul erkennt nur, was NER/Cues leisten.
"""
