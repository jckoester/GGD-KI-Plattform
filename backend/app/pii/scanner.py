"""PII-Scan: Name + Wohnort (Phase 14, Schritt 2).

``scan(text) -> list[PiiSpan]`` kombiniert drei Quellen und wendet die Schwellen aus
D-A/D-B an:

- **Cue-Namen (case-unabhängig):** Selbst-/Beziehungs-/Titel-Cue + folgender Eigenname
  → Name (fängt kleingeschriebene Eigennamen, die die cased NER verpasst).
- **NER `PER` (≥2 Tokens):** Vor+Nachname → Name. Einzelner Eigenname OHNE Cue wird
  bewusst NICHT gewarnt (unterdrückt einzelne Prominenten-Nachnamen wie „Goethe").
- **Wohnort:** vollständige Adresse (Straße+Nr. / PLZ) ODER NER `LOC` in einem Satz mit
  Wohn-Cue. Ein bloßer Ortsname ohne Bezug (Themen-Nennung) warnt NICHT.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_SPACY_MODEL = "de_core_news_md"
_nlp = None


def _get_nlp():
    """Lädt das spaCy-Modell einmalig (gecachter Singleton)."""
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load(_SPACY_MODEL)
        logger.info("PII: spaCy-Modell '%s' geladen", _SPACY_MODEL)
    return _nlp


@dataclass(frozen=True)
class PiiSpan:
    category: str  # "name" | "wohnort"
    start: int
    end: int
    text: str


# ── Muster (case-insensitive) ───────────────────────────────────────────────

# Ein Namens-Token: ≥2 Buchstaben (inkl. Umlaute/Akzente), interne Bindestriche/Apostrophe.
_NAME_TOKEN = r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’-]+"

# Cues, nach denen ein folgender Eigenname als persönlich gilt (→ Warnung).
_NAME_CUES = [
    r"ich\s+heiße", r"ich\s+heisse", r"mein\s+name\s+ist",
    r"ich\s+bin\s+der", r"ich\s+bin\s+die",
    r"mein(?:e)?\s+(?:bruder|schwester|freund(?:in)?|kumpel|mutter|vater|"
    r"oma|opa|cousin(?:e)?|lehrer(?:in)?)",
    r"(?:herr|frau)(?:\s+dr\.?)?",
]
_NAME_CUE_RE = re.compile(
    r"(?:" + "|".join(_NAME_CUES) + r")\s+(" + _NAME_TOKEN + r")",
    re.IGNORECASE,
)

# Wohn-Cues — wenn im selben Satz, warnen LOC-Entitäten dieses Satzes.
_RESIDENCE_CUES = [
    r"wohne", r"wohnst", r"wohnt", r"wohnhaft", r"wohnen", r"wohnort", r"lebe",
    r"komme\s+aus", r"komm\s+aus", r"kommt\s+aus", r"stamm[e]?\s+aus",
    # Umzugs-Verben (separable, daher tokenweise statt als feste Phrase):
    r"\bzieh(?:e|en|t|st)?\b", r"\bzog\b", r"\bgezogen\b", r"umzieh\w*", r"umgezogen",
    r"adresse",
]
_RESIDENCE_RE = re.compile(r"(?:" + "|".join(_RESIDENCE_CUES) + r")", re.IGNORECASE)

# Adresse: Straße + Hausnummer ODER PLZ + Ort (strukturell starkes Signal).
_ADDRESS_RE = re.compile(
    r"\b[A-ZÄÖÜ][\wäöüß.-]*"
    r"(?:straße|strasse|str\.|weg|allee|gasse|platz|ring|damm|ufer)\s+\d+[a-z]?\b"
    r"|\b\d{5}\s+[A-ZÄÖÜ][\wäöüß-]+",
    re.UNICODE,
)


def _merge(raw: list[tuple[str, int, int]], text: str) -> list[PiiSpan]:
    """Überlappende Spans gleicher Kategorie zur Vereinigung zusammenfassen."""
    out: list[list] = []  # [category, start, end]
    for cat, s, e in sorted(set(raw), key=lambda r: (r[1], r[2])):
        for item in out:
            if item[0] == cat and s < item[2] and item[1] < e:
                item[1] = min(item[1], s)
                item[2] = max(item[2], e)
                break
        else:
            out.append([cat, s, e])
    return [PiiSpan(cat, s, e, text[s:e]) for cat, s, e in out]


def scan(text: str) -> list[PiiSpan]:
    raw: list[tuple[str, int, int]] = []

    # 1. Cue-basierte Namen (case-unabhängig)
    for m in _NAME_CUE_RE.finditer(text):
        raw.append(("name", m.start(1), m.end(1)))

    # 2. Adressen
    for m in _ADDRESS_RE.finditer(text):
        raw.append(("wohnort", m.start(), m.end()))

    # 3. NER, satzweise (für den Wohn-Cue-Bezug)
    doc = _get_nlp()(text)
    for sent in doc.sents:
        has_res_cue = bool(_RESIDENCE_RE.search(sent.text))
        for ent in sent.ents:
            if ent.label_ == "PER":
                # D-B (b): nur Vor+Nachname (≥2 Nicht-Satzzeichen-Tokens)
                if sum(1 for t in ent if not t.is_punct) >= 2:
                    raw.append(("name", ent.start_char, ent.end_char))
            elif ent.label_ == "LOC" and has_res_cue:
                raw.append(("wohnort", ent.start_char, ent.end_char))

    return _merge(raw, text)
