"""Normalisierung von LLM-Roh-Extraktion zu CurriculumDraftData.

Komponente 4b aus KS-Phase-6-Schritt-2a (Revision 2).

Diese Datei enthält die deterministische Normalisierungslogik, die die verbatim
Felder aus der LLM-Extraktion in die finalen Referenz-Schlüssel umwandelt.

Leitprinzip: Alle Referenz-Schlüssel (IK, PK, LP) werden hier deterministisch gebaut,
nie vom LLM. Das LLM liefert nur die Roh-Daten (verbatim), diese Normalisierung
operiert auf der standardisierten BP-2016-Notation.
"""

import re
from typing import Any

from app.context.schemas import (
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
)


# Regex-Patterns für die Normalisierung
_IK_ITEM_RE = re.compile(r'\[?\(\s*(\d+)\s*\)')  # findet (1), (18), auch in [...]
_PK_GROUP_RE = re.compile(r'(?m)^\s*(\d+\.\d+)\s+\D')  # "2.4 Mit symbolischen…"
_PK_ITEM_RE = re.compile(r'(?m)^\s*(\d+)\.');  # "1. zwischen…", "3. …"
_LP_RE = re.compile(r'\(?L\)?\s+(BO|BTV|BNE|MB|VB|PG|BBO)\b', re.IGNORECASE)


def _normalize_ref(ref: str) -> str:
    """Normalisiert eine Referenz für toleranten Vergleich.
    
    Entfernt Leerzeichen, vereinheitlicht Klammern und Punkte.
    Wird für resolve_ik_node und resolve_pk_node verwendet.
    """
    if not ref:
        return ""
    # Leerzeichen entfernen
    ref = ref.replace(" ", "")
    # Klammern vereinheitlichen
    ref = ref.replace("[", "(").replace("]", ")")
    # Doppelte Punkte entfernen
    ref = ref.replace(".(", "(").replace(")", ".")
    return ref


_IK_PARTIAL_RE = re.compile(r'\[\s*\(\s*(\d+)\s*\)')  # [(N) — Item in eckigen Klammern


def _split_lines(text: str) -> list[str]:
    """Teilt Text an echten Zeilenumbrüchen UND am ↵-Trennzeichen der Serialisierung."""
    return text.replace('↵', '\n').splitlines()


def _extract_ik_items(text: str) -> list[tuple[str, bool]]:
    """Extrahiert IK-Items aus ik_raw Text.

    Rückgabe: Liste von (ik_nummer, ist_partiell) Tuples.
    Partiell = nur wenn das konkrete (N) in eckigen Klammern steht: [(N)…].
    Ellipsen-Klammern im Fließtext wie "(6) […] Text" gelten NICHT als partiell.
    """
    if not text:
        return []

    partial_nums = {m.group(1) for m in _IK_PARTIAL_RE.finditer(text)}
    items = []
    for num in _IK_ITEM_RE.findall(text):
        items.append((num, num in partial_nums))
    return items


def _extract_pk_items(pk_raw: str) -> list[str]:
    """Extrahiert PK-Referenzen aus pk_raw Text.

    Verarbeitet zeilenweise (trennt an ↵ und \\n):
    - Zeilen die mit "X.Y Text" beginnen → Gruppe merken
    - Zeilen die mit "N. Text" beginnen → Item zu aktueller Gruppe

    Rückgabe: Liste von PK-Schlüsseln wie ["2.5.1", "2.4.1", "2.4.3", "2.4.5"]
    """
    if not pk_raw:
        return []

    pks = []
    current_group = None

    for line in _split_lines(pk_raw):
        line = line.strip()
        if not line:
            continue

        group_match = _PK_GROUP_RE.match(line)
        if group_match:
            current_group = group_match.group(1)
            continue

        item_match = _PK_ITEM_RE.match(line)
        if item_match and current_group:
            pks.append(f"{current_group}.{item_match.group(1)}")

    return pks


def _extract_lp_codes_from_text(text: str | None) -> list[str]:
    """Extrahiert Leitperspektive-Codes aus Text.
    
    Findet Muster wie "L BO", "(L) BTV", "LP-MB" etc.
    """
    if not text:
        return []
    return _LP_RE.findall(text)


def normalize_raw_to_draft(
    raw_kapitel: Any,
    chapter_index: int
) -> CurriculumDraftKapitel:
    """Normalisiert RawKapitelExtraction zu CurriculumDraftKapitel.
    
    Args:
        raw_kapitel: Das Roh-Kapitel aus der LLM-Extraktion
        chapter_index: Die Reihenfolge-Nummer (0-basiert)
    
    Returns:
        CurriculumDraftKapitel mit normalisierten Referenzen
    """
    lernsequenzen = []
    
    for raw_ls_idx, raw_ls in enumerate(raw_kapitel.get('lernsequenzen', [])):
        eintraege = []
        
        # Aktueller IK-Abschnitt
        ik_abschnitt = raw_ls.get('ik_abschnitt')
        
        # Alle RawEntries verarbeiten
        for raw_entry in raw_ls.get('eintraege', []):
            # IK-Items extrahieren und für jedes Item einen Eintrag erstellen
            ik_raw = raw_entry.get('ik_raw', '')
            pk_raw = raw_entry.get('pk_raw', '')
            pk_merged = raw_entry.get('pk_merged_from_above', False)
            konkretisierung = raw_entry.get('konkretisierung')
            hinweise = raw_entry.get('hinweise')
            confidence = raw_entry.get('confidence', 1.0)
            warnings = raw_entry.get('warnings', [])
            
            # IK-Items extrahieren
            ik_items = _extract_ik_items(ik_raw) if ik_raw else []
            
            # PK-Items extrahieren
            if pk_raw and not pk_merged:
                current_pks = _extract_pk_items(pk_raw)
            elif pk_merged:
                # Vererbung: leere Liste, wird später gefüllt
                current_pks = []
            else:
                current_pks = []
            
            # LP-Codes extrahieren
            lp_codes = _extract_lp_codes_from_text(hinweise)
            
            # Für jedes IK-Item einen Eintrag erstellen (Fan-out)
            if not ik_items:
                # Keine IK-Items gefunden, einen Eintrag mit dem Raw-IK erstellen
                entry = CurriculumDraftEntry(
                    ik=ik_raw if ik_raw else None,
                    ik_partiell=False,
                    pk=current_pks if current_pks else [],
                    konkretisierung=konkretisierung,
                    hinweise=hinweise,
                    lp=lp_codes,
                    confidence=confidence,
                    warnings=warnings + ["Keine IK-Items extrahiert"] if ik_raw else warnings
                )
                eintraege.append(entry)
            else:
                for ik_num, is_partiell in ik_items:
                    # IK-Schlüssel bauen: ik_abschnitt + ".(" + ik_num + ")"
                    if ik_abschnitt:
                        ik_key = f"{ik_abschnitt}.({ik_num})"
                    else:
                        ik_key = None
                        warnings.append(f"Kein IK-Abschnitt für Item {ik_num}")
                    
                    entry = CurriculumDraftEntry(
                        ik=ik_key,
                        ik_partiell=is_partiell,
                        pk=current_pks if current_pks else [],
                        konkretisierung=konkretisierung,
                        hinweise=hinweise,
                        lp=lp_codes,
                        confidence=confidence,
                        warnings=warnings.copy()
                    )
                    eintraege.append(entry)
        
        # Lernsequenz erstellen
        ls = CurriculumDraftLernsequenz(
            bp_titel=raw_ls.get('bp_titel'),
            bp_leitidee=None,
            reihenfolge=raw_ls_idx + 1,
            eintraege=eintraege,
            confidence=raw_ls.get('confidence', 1.0),
            warnings=raw_ls.get('warnings', [])
        )
        lernsequenzen.append(ls)
    
    # Kapitel erstellen
    return CurriculumDraftKapitel(
        titel=raw_kapitel.get('titel', f'Kapitel {chapter_index + 1}'),
        reihenfolge=chapter_index + 1,
        std=raw_kapitel.get('std'),
        hinweis=raw_kapitel.get('einleitung'),
        konkretisierung=[],
        lernsequenzen=lernsequenzen,
        confidence=raw_kapitel.get('confidence', 1.0),
        warnings=raw_kapitel.get('warnings', [])
    )


def normalize_raw_extraction(raw_data: dict[str, Any]) -> list:
    """Normalisiert die komplette LLM-Roh-Extraktion.
    
    Args:
        raw_data: Die Roh-Daten aus dem LLM (mit kapitel Feld)
    
    Returns:
        Liste von CurriculumDraftKapitel
    """
    chapters = []
    raw_chapters = raw_data.get('kapitel', [])
    
    if isinstance(raw_chapters, dict):
        # Einzelnes Kapitel
        raw_chapters = [raw_chapters]
    
    for idx, raw_chapter in enumerate(raw_chapters):
        chapter = normalize_raw_to_draft(raw_chapter, idx)
        chapters.append(chapter)
    
    return chapters


# Tolerante Referenz-Normalisierung für resolve-Funktionen

def normalize_ik_ref(ik_ref: str) -> str:
    """Normalisiert eine IK-Referenz für toleranten Vergleich."""
    return _normalize_ref(ik_ref)


def normalize_pk_ref(pk_ref: str) -> str:
    """Normalisiert eine PK-Referenz für toleranten Vergleich."""
    return _normalize_ref(pk_ref)
