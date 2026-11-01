"""Audit-Helfer (0.28, `app/core/audit.py`): Positivliste, verbotene Felder, Rolle — und der
Wächter, dass niemand an ihm vorbei in `audit_log` schreibt."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.audit import EREIGNISSE, eintrag

APP = Path(__file__).resolve().parents[2] / "app"


def test_unbekanntes_ereignis_oder_kategorie_wirft():
    with pytest.raises(ValueError, match="unbekanntes Ereignis"):
        eintrag("admin", "gibt_es_nicht")
    with pytest.raises(ValueError, match="unbekannte Kategorie"):
        eintrag("quatsch", "login_failed")


@pytest.mark.parametrize("daten", [
    {"text": "Ich will nicht mehr"},
    {"message_text": "x"},
    {"meldung": {"kontakt": "Jan, 10b"}},
    {"systemprompt": "Du bist …"},
    {"liste": [{"inhalt": "x"}]},
    {"ip": "10.0.0.1"},
])
def test_verbotene_felder_werden_abgewiesen(daten):
    with pytest.raises(ValueError, match="gehört nicht ins Protokoll"):
        eintrag("admin", "assistant_approved", daten=daten)


def test_kennungen_zahlen_und_wahrheitswerte_sind_erlaubt():
    z = eintrag("admin", "feedback_status_changed", daten={
        "message_id": "abc", "max_tokens": 4000, "hat_kontakt": True, "status": "erledigt",
        "beschreibung_geaendert": True,
    })
    assert z.payload["status"] == "erledigt"


def test_akteur_aus_jwt_mit_fuehrender_rolle_und_ziel():
    user = SimpleNamespace(sub="pseudo-1", roles=["teacher", "admin"])
    z = eintrag("admin", "assistant_deleted", akteur=user, ziel=("assistant", 42))
    assert (z.actor_pseudonym, z.actor_role, z.target_type, z.target_id) == ("pseudo-1", "admin", "assistant", "42")
    assert z.retention_class == "admin"
    assert eintrag("system", "accounts_cleaned").actor_pseudonym is None


def test_vorschau_ereignisse_sind_vorbereitet():
    assert {"preview_entered", "preview_exited"} <= EREIGNISSE["auth"]


def test_niemand_schreibt_am_helfer_vorbei():
    """`AuditLog(` und `INSERT INTO audit_log` nur im Helfer — die Positivliste und die
    Sperre verbotener Felder gelten sonst nicht."""
    erlaubt = {"core/audit.py", "db/models.py"}
    treffer = sorted(
        str(p.relative_to(APP)) for p in APP.rglob("*.py")
        if "__pycache__" not in p.parts and str(p.relative_to(APP)) not in erlaubt
        and ("AuditLog(" in (t := p.read_text(encoding="utf-8")) or "INSERT INTO audit_log" in t)
    )
    assert treffer == []
