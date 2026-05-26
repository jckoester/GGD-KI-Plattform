"""Referenz-Token-Klassifikation und Text-Normalisierung."""

import re

_LP_PATTERN = re.compile(r'^(BNE|BTV|PG|BO|MB|VB|LFDB)_\d{2}$')
_PK_PATTERN = re.compile(r'BP\w+_PK_')
_IK_PATTERN = re.compile(r'BP\w+_IK_')


def strip_soft_hyphens(text: str) -> str:
    """Entfernt Soft-Hyphens (U+00AD) aus Text."""
    return text.replace('\u00ad', '')


def classify_reference(token: str) -> dict | None:
    """
    Klassifiziert einen Referenz-Token aus der IK-Tabellen-Referenzspalte.

    Gibt {'target_bp_id': str, 'type': str} zurueck, oder None wenn unbekannt.

    Relationstypen:
    - 'develops'   -> BP*_PK_* (IK-Standard verweist auf PK-Kompetenz)
    - 'related_to' -> BP*_IK_* (fachuebergreifender IK-Querverweis, "siehe auch")
    - 'references' -> LP-Kurzcode wie BNE_01, MB_05 (Leitperspektive-Aspekt)
    """
    token = token.strip()
    if not token:
        return None
    if _LP_PATTERN.match(token):
        return {'target_bp_id': token, 'type': 'references'}
    if _PK_PATTERN.search(token):
        return {'target_bp_id': token, 'type': 'develops'}
    if _IK_PATTERN.search(token):
        return {'target_bp_id': token, 'type': 'related_to'}
    return None
