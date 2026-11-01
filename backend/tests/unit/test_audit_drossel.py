"""Sperre der Drossel im Audit-Log (0.28): höchstens ein Eintrag je Eimer, Person und
Viertelstunde — und nur auf dem Pseudonym-Weg, nie mit einem Zugangstoken."""
from types import SimpleNamespace
from unittest.mock import patch

from app.ratelimit import dependency


def test_sperre_wird_einmal_je_viertelstunde_protokolliert(monkeypatch):
    monkeypatch.setattr(dependency, "_ZULETZT_PROTOKOLLIERT", {})
    nutzer = SimpleNamespace(sub="pseudo-x", roles=["student"])
    with patch("app.core.hintergrund.im_hintergrund") as start:
        for _ in range(5):
            dependency._sperre_protokollieren("chat", nutzer)
        dependency._sperre_protokollieren("upload", nutzer)
    assert start.call_count == 2          # chat einmal, upload einmal
