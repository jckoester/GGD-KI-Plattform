"""Was das Modell über die Plan-Operationen liest (Paket 5, AP6).

⚠️ **Eine Werkzeugbeschreibung ist Verhaltensschnittstelle, kein Kommentar.** Sie ist
das Einzige, woraus ein Modell die Wahl zwischen zwei ähnlichen Operationen ableiten
kann — eine Planungs-Anleitung (System-Prompt) gibt es im Code nicht.

Der Anlass (24.09.2026): Nach „Stunden verschieben" stand am Zieltermin nur das Thema.
Das Modell hatte `set_topic` gewählt, wo `move_content` gemeint war — und die
Beschreibung war eine Liste von **Signaturen** ohne Bedeutung:

    "Operationen, je mit 'op': move_content{from_slot_id,to_slot_id},
     swap_content{slot_a,slot_b}, set_topic{slot_id,thema}, …"

Wer „setze das Thema auf den nächsten Termin" denkt, greift danach zu `set_topic`.
"""
import pytest

import app.planning.assistant_tools  # noqa: F401  — registriert die Werkzeuge
from app.chat.tools import TOOL_REGISTRY


@pytest.fixture
def op_beschreibung():
    f = TOOL_REGISTRY["apply_plan_operations"].definition["function"]
    return f["description"] + "\n" + f["parameters"]["properties"]["operations"]["description"]


def test_move_content_nennt_was_es_mitnimmt(op_beschreibung):
    """Ohne diesen Satz ist `move_content` nur ein Name."""
    stelle = op_beschreibung[op_beschreibung.index("move_content{"):]
    satz = stelle[: stelle.index("\n")]
    for wort in ("Thema", "Unterrichtseinheit", "Stundenentwurf"):
        assert wort in satz, f"{wort} fehlt in der Beschreibung von move_content"


def test_set_topic_sagt_was_es_nicht_tut(op_beschreibung):
    """⚠️ Der entscheidende Satz. `set_topic` klingt nach „Thema setzen" — genau das ist
    es, und genau deshalb wurde es für eine Verlegung missbraucht."""
    stelle = op_beschreibung[op_beschreibung.index("set_topic{"):]
    satz = stelle[: stelle.index("\n")]
    assert "NUR" in satz or "nur" in satz
    assert "falsch" in satz or "bleiben" in satz


def test_die_wahl_steht_in_der_hauptbeschreibung(op_beschreibung):
    """Nicht nur bei den Parametern: Manche Modelle lesen die Kurzbeschreibung genauer."""
    kurz = TOOL_REGISTRY["apply_plan_operations"].definition["function"]["description"]
    assert "move_content" in kurz and "set_topic" in kurz


@pytest.mark.parametrize("op", [
    "move_content", "swap_content", "set_topic", "set_unit", "set_category",
    "mark_needs_adjustment", "transfer_phases", "shorten_phase", "strike_phase",
])
def test_jede_operation_wird_erklaert(op_beschreibung, op):
    """⚠️ Jede, nicht nur die beiden aus dem Vorfall.

    Sonst bliebe die nächste Verwechslung genauso unvorbereitet — und sie fiele
    wieder erst im Betrieb auf.
    """
    stelle = op_beschreibung.index(f"{op}{{")
    satz = op_beschreibung[stelle:].split("\n")[0]
    # Hinter der Signatur muss Text stehen, nicht nur ein Komma zur nächsten.
    nach_signatur = satz[satz.index("}") + 1:].strip(" :,")
    assert len(nach_signatur) > 25, f"{op} ist nicht erklärt: {nach_signatur!r}"


def test_ein_entfall_muss_eigens_eingetragen_werden(op_beschreibung):
    """⚠️ **Der zweite Vorfall, 24.09.2026** (M 9C, 25.09.):

    Das Verschieben klappte — `move_content` brachte Einheit und Entwurf ans Ziel. Den
    mitgeteilten **Entfall** trug das Modell aber nicht ein: Der Quelltermin blieb eine
    reguläre, **leere** Stunde. Folge: Die Stundenbilanz zählt ihn weiter als gehalten,
    `jetzt.py` hält ihn für die zuletzt gehaltene Stunde, und die Jahresplanung zeigt
    eine leere Stunde, wo ein Ausfall war.

    `move_content` **soll** die Kategorie nicht anfassen — eine Verlegung ohne Entfall
    ist legitim (eine Einheit nach vorn zusammenziehen). Also muss die Beschreibung
    sagen, dass beides zusammengehört.
    """
    assert "set_category" in op_beschreibung
    stelle = op_beschreibung[op_beschreibung.index("move_content{"):]
    satz = stelle[: stelle.index("\n")]
    assert "Kategorie" in satz, "move_content sagt nicht, dass es die Kategorie nicht ändert"


def test_die_regel_steht_auch_in_der_kurzbeschreibung():
    """Manche Modelle lesen die Kurzbeschreibung genauer als die Parameter."""
    kurz = TOOL_REGISTRY["apply_plan_operations"].definition["function"]["description"]
    assert "Ausfall" in kurz and "set_category" in kurz
