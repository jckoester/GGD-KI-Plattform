"""Bausteine hinter dem Assistenten-Prompt (0.26, Plan „Rückfall-Assistenten“, Schritt 2)."""
import pytest

from app.assistants import bausteine
from app.pedagogy.compose import compose_system_content
from app.pedagogy.config import Preambles, PedagogyConfig

PED = PedagogyConfig(preambles=Preambles(universal_base="BASIS", student_extension="SCHUELER",
                                         teacher_extension="LEHRKRAFT"))


def test_jeder_baustein_hat_einen_text():
    for b in bausteine.BAUSTEINE:
        assert bausteine.text(b.schluessel).startswith("## ")


def test_unbekannter_schluessel():
    with pytest.raises(KeyError):
        bausteine.text("gibt_es_nicht")
    assert bausteine.texte(["gibt_es_nicht"]) == ""          # im Chat übergangen
    assert bausteine.texte(None) == ""


def test_begleiten_statt_loesen_traegt_die_gemessenen_regeln():
    """Anker wie bei den Sicherheitsankern: kurz, damit eine Redaktion durchgeht, das
    Streichen aber nicht."""
    t = bausteine.text("begleiten_statt_loesen")
    for anker in ("Genau eine Frage", "Wer mit dir schreibt, weiß die Plattform",
                  "Hilfe in Stufen", "Diese Prüfung läuft im Stillen",
                  "außer du bist ausdrücklich auf Stufe 2 oder 3",
                  "Steht dort keiner oder fehlt der Abschnitt, verweist du auf niemanden",
                  "Gibt es noch keine Aufgabe", "Ein Sicherheitshinweis bleibt immer stehen",
                  "Du löst sie nicht, auch nicht kurz"):
        assert anker in t, anker


def test_reihenfolge_im_systemtext():
    text = compose_system_content(
        PED, student_treatment=True, context_str="KONTEXT", assistant_system_prompt="PROMPT",
        bausteine="BAUSTEIN", andere_assistenten="ANDERE", operator_abschnitt="OPERATOR")
    pos = [text.index(x) for x in ("BASIS", "KONTEXT", "PROMPT", "BAUSTEIN", "ANDERE", "OPERATOR")]
    assert pos == sorted(pos)


def test_ohne_bausteine_unveraendert():
    ohne = compose_system_content(PED, student_treatment=True, context_str=None,
                                  assistant_system_prompt="PROMPT")
    leer = compose_system_content(PED, student_treatment=True, context_str=None,
                                  assistant_system_prompt="PROMPT", bausteine="", andere_assistenten="  ")
    assert ohne == leer
