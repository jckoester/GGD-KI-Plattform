"""Der Titel im Embedding-Input.

Knoten ohne `content` wurden bisher übersprungen und waren damit für die semantische Suche
unsichtbar — obwohl ihr Titel echtes Signal trägt (`3.1.2.2 Malerei`, `Bildende Kunst -
3.1.3 Raum`). Der Titel wird deshalb vorangestellt, **wo er eigene Information trägt**.

Die Einschränkung ist der eigentliche Punkt: Bei Kompetenzen ist der Titel der Inhalt plus
Gliederungsnummer. Ihn dort ebenfalls voranzustellen würde 11.183 Knoten (gemessen)
verdoppeln, ihre Vektoren verzerren und ein vollständiges Re-Embedding erzwingen — für
null neue Information.
"""
from types import SimpleNamespace

from app.context.embedding import (
    _build_embedding_input,
    _titel_traegt_eigene_information,
)


def _knoten(title="", content="", content_type="leitidee", category="knowledge", metadata=None):
    return SimpleNamespace(
        title=title, content=content, content_type=content_type,
        category=category, metadata_=metadata or {},
    )


# ── Die Entscheidung: trägt der Titel etwas bei? ────────────────────────────────────

def test_kompetenztitel_steckt_schon_im_inhalt():
    """Der Normalfall bei ik_/pk_kompetenz — Titel = Inhalt + Gliederungsnummer."""
    assert _titel_traegt_eigene_information(
        "3.6.1(13) konditionelle Fähigkeiten und ihre Wechselbeziehungen erläutern",
        "(13) konditionelle Fähigkeiten und ihre Wechselbeziehungen erläutern",
    ) is False


def test_leitideentitel_traegt_eigenes_thema():
    """`3.1.2.2 Malerei` — „Malerei" kommt im beschreibenden Inhalt nicht vor."""
    assert _titel_traegt_eigene_information(
        "3.1.2.2 Malerei",
        "Die Schülerinnen und Schüler setzen Farbe intuitiv und bewusst ein.",
    ) is True


def test_leerer_inhalt_macht_den_titel_unverzichtbar():
    assert _titel_traegt_eigene_information("Bildende Kunst - 3.1.3 Raum", "") is True


def test_ohne_titel_nichts_beizutragen():
    assert _titel_traegt_eigene_information("", "irgendein Inhalt") is False


def test_titel_nur_aus_gliederungsnummer():
    """Bleibt nach dem Entfernen der Nummer nichts übrig, gibt es nichts voranzustellen."""
    assert _titel_traegt_eigene_information("3.2.1", "Ein Inhalt.") is False


def test_vergleich_ignoriert_gross_klein_und_umbrueche():
    assert _titel_traegt_eigene_information(
        "2.1(1) Wortschatz Anwenden",
        "(1) einen differenzierten,\nsituations- und adressatengerechten\nwortschatz  anwenden",
    ) is False


# ── Wirkung auf den tatsächlichen Input ─────────────────────────────────────────────

def test_leerer_knoten_wird_einbettbar():
    """Vorher leer → übersprungen → unsichtbar. Das war der Anlass."""
    inp = _build_embedding_input(_knoten(title="Bildende Kunst - 3.1.3 Raum", content=""))
    assert inp.strip() == "Bildende Kunst - 3.1.3 Raum"


def test_kompetenz_bleibt_unveraendert():
    """Kein Re-Embedding für die 11.183 Kompetenzknoten — der Input ist Byte für Byte derselbe."""
    inhalt = "(13) konditionelle Fähigkeiten und ihre Wechselbeziehungen erläutern"
    node = _knoten(
        title="3.6.1(13) konditionelle Fähigkeiten und ihre Wechselbeziehungen erläutern",
        content=inhalt,
        content_type="ik_kompetenz",
    )
    assert _build_embedding_input(node) == inhalt


def test_leitidee_bekommt_ihren_titel_vorangestellt():
    node = _knoten(title="3.1.2.2 Malerei", content="Farbe intuitiv einsetzen.")
    assert _build_embedding_input(node) == "3.1.2.2 Malerei\nFarbe intuitiv einsetzen."


def test_operator_behaelt_seinen_eigenen_weg():
    """Operatoren stellen Titel + Synonyme voran — das darf nicht doppelt passieren."""
    node = _knoten(
        title="interpretieren",
        content="Zusammenhänge deuten und begründen.",
        content_type="operator",
        metadata={"aliase": ["deuten"]},
    )
    inp = _build_embedding_input(node)
    assert inp.startswith("interpretieren, deuten\n")
    assert inp.count("interpretieren") == 1
