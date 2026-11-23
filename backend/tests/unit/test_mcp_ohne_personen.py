"""F6: Keine Personen in den Antworten des MCP-Servers (0.54, Päckchen AW)."""
from uuid import uuid4

from app.mcp.werkzeuge import PERSONENFELDER, _ohne_personen


def test_personenfelder_fliegen_auch_verschachtelt_raus():
    kennung = uuid4()
    roh = {"titel": "Physik", "owner_pseudonym": "p1", "curriculum_id": kennung,
           "kapitel": [{"titel": "Optik", "created_by": "p2", "lernsequenzen": [{"autor": "p3", "std": 4}]}]}
    assert _ohne_personen(roh) == {"titel": "Physik", "curriculum_id": str(kennung),
                                   "kapitel": [{"titel": "Optik", "lernsequenzen": [{"std": 4}]}]}


def test_die_bekannten_felder():
    assert {"owner_pseudonym", "created_by", "pseudonym"} <= PERSONENFELDER
