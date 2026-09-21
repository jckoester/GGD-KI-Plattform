"""Wer ein Curriculum lesen darf (Entscheidung Jan, 21.09.2026).

**Nur `private` schränkt ein.** Curricula sind kein Geheimnis; die Leseprüfung des
Curriculum-Baums folgt damit derselben Linie wie `read_scope_clause`, wo `OFFENE_SCOPES`
genau `global`, `school` und `subject` umfasst.

Bis zum 21.09.2026 wies ein zweiter Zweig Schüler:innen bei `read_scope == 'subject'`
ab, außer `CURRICULUM_VISIBLE_TO_STUDENTS` war gesetzt. Er war wirkungslos (kein
Curriculum trägt diesen Scope, keine Stelle setzt ihn) und stand zugleich quer zur
allgemeinen Regel, die `subject` als **offen** führt — über jeden anderen Lesepfad war
ein so markierter Knoten ohnehin sichtbar. Diese Tests halten den Zustand danach fest.
"""
import pytest
from fastapi import HTTPException

from app.context.router import _check_curriculum_read_permission
from app.context.visibility import OFFENE_SCOPES


class _Nutzer:
    def __init__(self, sub, rollen):
        self.sub = sub
        self.roles = rollen


SCHUELERIN = _Nutzer("schuelerin-1", ["student"])
LEHRKRAFT = _Nutzer("lehrkraft-1", ["teacher"])


@pytest.mark.parametrize("scope", OFFENE_SCOPES)
def test_offene_scopes_stehen_allen_offen(scope):
    """Gekoppelt an `OFFENE_SCOPES`: Wer dort etwas ergänzt, bekommt es hier mitgeprüft.

    Wer `subject` dort **entfernt**, muss hier eine Entscheidung treffen — der Test
    schlägt dann nicht an, aber die Liste, über die er läuft, ist dieselbe.
    """
    _check_curriculum_read_permission({"read_scope": scope}, SCHUELERIN)
    _check_curriculum_read_permission({"read_scope": scope}, LEHRKRAFT)


def test_die_umgebung_entscheidet_nicht_mehr_mit(monkeypatch):
    """Die Gegenprobe zur entfernten Variablen: Sie hat keine Wirkung mehr.

    Stünde der alte Zweig noch da, wiese dieser Aufruf mit 403 ab — die Variable ist
    ja nicht gesetzt.
    """
    monkeypatch.delenv("CURRICULUM_VISIBLE_TO_STUDENTS", raising=False)
    _check_curriculum_read_permission({"read_scope": "subject"}, SCHUELERIN)


def test_fremdes_privates_bleibt_zu():
    with pytest.raises(HTTPException) as fehler:
        _check_curriculum_read_permission(
            {"read_scope": "private", "owner_pseudonym": "jemand-anders"}, LEHRKRAFT
        )
    assert fehler.value.status_code == 403


def test_eigenes_privates_ist_lesbar():
    _check_curriculum_read_permission(
        {"read_scope": "private", "owner_pseudonym": LEHRKRAFT.sub}, LEHRKRAFT
    )


def test_ohne_angabe_gilt_school():
    """Der Vorgabewert des Baums — ein Curriculum ohne Scope ist nicht versehentlich zu."""
    _check_curriculum_read_permission({}, SCHUELERIN)
