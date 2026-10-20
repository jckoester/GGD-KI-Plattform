"""Das Angebot der Vorab-Suche im Prompt, der Vorrangsatz und der Messkanal (0.16, Schritt 3b).

Die Auswahl selbst prüft `tests/integration/test_vorab_suche_db.py` (`TestAngebot`); hier
geht es um das, was daraus im Prompt und im Strom wird.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.chat.router import _vorab_debug_ereignis
from app.context.bausteine import WERKZEUG, Angebot, Baustein
from app.context.service import _vorab_block
from app.pedagogy.compose import compose_system_content
from app.pedagogy.config import PedagogyConfig, Preambles, invalidate_pedagogy_cache, load_pedagogy

VORRANG = ("Für Fachliches gilt der Wissensspeicher der Schule: Was dort steht, hat Vorrang vor "
           "deinem eigenen Wissen.")
BEISPIEL = Path(__file__).resolve().parents[3] / "config" / "pedagogy.example.yaml"

ANGEBOT = [Angebot("n-1", "Elektronegativität", "Chemie", "nennung"),
           Angebot("n-2", "Gruppenpuzzle", None, "distanz")]


# ── Satz im Prompt ────────────────────────────────────────────────────────────

def test_angebot_allein_heisst_dazu():
    block = _vorab_block([], ANGEBOT)
    assert block == (
        "Im Wissensspeicher der Schule gibt es dazu: Elektronegativität (Chemie), Gruppenpuzzle "
        "— den Inhalt holst du mit dem Werkzeug, wenn er für die Antwort zählt."
    )


def test_angebot_hinter_sicheren_eintraegen_heisst_ausserdem():
    block = _vorab_block([{"title": "Ion"}], ANGEBOT[:1])
    json_teil, satz = block.rsplit("\n\n", 1)
    assert '"title": "Ion"' in json_teil
    assert "automatisch zur letzten Nachricht" in json_teil
    assert satz.startswith("Im Wissensspeicher der Schule gibt es außerdem: Elektronegativität (Chemie)")


def test_ohne_angebot_bleibt_der_block_wie_bisher():
    """Gegenprobe: Ohne Angebot kein Satz — die sichere Stufe allein sieht aus wie bis 0.15."""
    block = _vorab_block([{"title": "Ion"}])
    assert "gibt es" not in block
    assert block.endswith("Brauchst du etwas anderes, such mit deinem Werkzeug.")


# ── Vorrangsatz aus pedagogy.yaml ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _frischer_cache():
    invalidate_pedagogy_cache()
    yield
    invalidate_pedagogy_cache()


def _mit_vorrang(wert: str) -> PedagogyConfig:
    ped = load_pedagogy()
    return ped.model_copy(update={
        "preambles": ped.preambles.model_copy(update={"wissensspeicher_vorrang": wert}),
    })


def _prompt(ped: PedagogyConfig) -> str:
    return compose_system_content(ped, student_treatment=True, context_str=None,
                                  assistant_system_prompt=None)


def _basis_dann_erweiterung(ped: PedagogyConfig) -> str:
    """Basis und Erweiterung direkt hintereinander — so steht es ohne Vorrangsatz da."""
    return f"{ped.preambles.universal_base.strip()}\n\n{ped.preambles.student_extension.strip()}"


def test_ohne_schluessel_kein_vorrangsatz():
    """Eine bestehende `pedagogy.yaml` ohne den Schlüssel lädt weiter — ohne Satz im Prompt."""
    preambles = Preambles.model_validate(
        {"universal_base": "B", "student_extension": "S", "teacher_extension": "L"})
    assert preambles.wissensspeicher_vorrang == ""
    ped = _mit_vorrang(preambles.wissensspeicher_vorrang)
    assert _basis_dann_erweiterung(ped) in _prompt(ped)


def test_leerer_wert_laesst_ihn_weg():
    ped = _mit_vorrang("  \n")
    assert _basis_dann_erweiterung(ped) in _prompt(ped)


def test_vorrangsatz_direkt_nach_der_basis():
    ped = _mit_vorrang(VORRANG)
    prompt = _prompt(ped)
    basis = ped.preambles.universal_base.strip()
    erweiterung = ped.preambles.student_extension.strip()
    assert f"{basis}\n\n{VORRANG}\n\n{erweiterung}" in prompt


def test_beispielkonfiguration_traegt_den_gemessenen_satz():
    daten = yaml.safe_load(BEISPIEL.read_text(encoding="utf-8"))
    assert PedagogyConfig.model_validate(daten).preambles.wissensspeicher_vorrang == VORRANG


# ── Messkanal `vorab_debug` ───────────────────────────────────────────────────

def _ereignis(umgebung: str):
    nachgeschlagen = [Baustein("n-1", "Elektronegativität", "begriff", "Chemie", WERKZEUG)]
    with patch("app.chat.router.settings") as mock_settings:
        mock_settings.environment = umgebung
        return _vorab_debug_ereignis(ANGEBOT, nachgeschlagen, ["Elektronegativität"])


def test_messkanal_ausserhalb_der_produktion():
    ereignis = _ereignis("development")
    kopf, daten = ereignis.split("\n", 1)
    assert kopf == "event: vorab_debug"
    assert json.loads(daten.removeprefix("data: ")) == {
        "angebot": [
            {"node_id": "n-1", "titel": "Elektronegativität", "fach": "Chemie", "quelle": "nennung"},
            {"node_id": "n-2", "titel": "Gruppenpuzzle", "fach": None, "quelle": "distanz"},
        ],
        "nachgeschlagen": ["n-1"],
        "suchanfragen": ["Elektronegativität"],
        "sicher_gruppe": [],
    }


def test_messkanal_nie_in_der_produktion():
    assert _ereignis("production") is None
