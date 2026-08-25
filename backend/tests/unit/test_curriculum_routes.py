"""Welche Curriculum-Endpunkte es gibt — und welchen es bewusst nicht mehr gibt.

`POST /context/curricula` nahm einen vollständigen Entwurf entgegen und legte daraus ein
Curriculum an. Der Endpunkt **committete nicht**, wurde von keiner Seite aufgerufen und
kein Test deckte ihn ab — die drei Eigenschaften haben einander gedeckt: Weil ihn niemand
benutzte, fiel nie auf, dass er nichts schrieb.

Entfernt am 2026-08-08. Dieser Test hält die Entscheidung fest, denn die naheliegende
„Reparatur" wäre gewesen, ein `db.commit()` nachzureichen — und damit einen ungenutzten
Schreibpfad tief in den Wissensgraph wiederzubeleben, den jede Lehrkraft hätte aufrufen
können. Der Weg für vollständige Entwürfe ist `scripts/import_curriculum.py`, ein
Admin-Vorgang auf der Kommandozeile (`docs/runbooks/curriculum-transfer.md`).
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

from app.context.router import router


def _routen() -> set[tuple[str, str]]:
    return {
        (methode, r.path)
        for r in router.routes
        if "curricula" in getattr(r, "path", "")
        for methode in r.methods
        if methode != "HEAD"
    }


def test_bulk_create_endpunkt_ist_entfernt():
    """Wiederbelebung nur mit ausdrücklicher Entscheidung — nicht aus Versehen."""
    assert ("POST", "/context/curricula") not in _routen(), (
        "`POST /context/curricula` ist zurück. Falls ein Curriculum-Import über die "
        "Oberfläche gewünscht ist: neu entwerfen (Vorschau, Rechteprüfung, "
        "Konfliktanzeige) und diesen Test anpassen — nicht den alten Stumpf wiederherstellen."
    )


def test_die_genutzten_endpunkte_sind_vollstaendig():
    """Die tatsächliche Oberfläche der Curriculum-API, als Zusage festgehalten.

    Ein neuer Endpunkt fällt hier auf und zwingt zu der Frage, die beim entfernten
    gefehlt hat: Wer ruft ihn auf, und schreibt er auch wirklich?
    """
    assert _routen() == {
        ("GET", "/context/curricula/{curriculum_id}"),
        ("GET", "/context/curricula/{curriculum_id}/export"),
        ("GET", "/context/curricula/by-subject/{subject_id}"),
        ("PATCH", "/context/curricula/{curriculum_id}"),      # Titel + Jahrgangsband
        ("POST", "/context/curricula/{curriculum_id}/relink"),
        ("POST", "/context/curricula/new"),                    # leeres Curriculum
    }


def test_schreibende_endpunkte_committen():
    """Die Ursache des entfernten Endpunkts war ein fehlendes Commit.

    `get_db` committet nicht (es schließt die Session nur), also muss jeder schreibende
    Endpunkt es selbst tun. Geprüft wird der Quelltext der beiden Funktionen, die
    Curriculum-Knoten anlegen bzw. ändern.
    """
    import inspect

    from app.context.router import create_curriculum_node, update_curriculum_meta

    for funktion in (create_curriculum_node, update_curriculum_meta):
        quelle = inspect.getsource(funktion)
        assert "db.commit()" in quelle, (
            f"{funktion.__name__} schreibt, committet aber nicht — die Änderung ginge "
            f"beim Schließen der Session verloren."
        )


# ── Leitperspektiven-Kürzel: aus bp_id ableiten (Punkt 3) ────────────────────
#
# `metadata.code` ist in echten Daten **nie** gesetzt — geprüft an allen 7
# Leitperspektiven und 48 Aspekten der Dev-Instanz. Export und Import hingen beide an
# diesem nie gefüllten Feld: Der Export ließ LP-Verweise als UUID stehen (in einer anderen
# Instanz wertlos), der Import löste Kürzel nie zu Knoten auf.

import pytest

from app.context.service import leitperspektive_code, normalize_lp_code


@pytest.mark.parametrize(
    "eingabe,erwartet",
    [
        ("BO", "BO"),
        ("L BO", "BO"),        # Schreibweise aus Entwurfsdaten
        ("(L) BTV", "BTV"),    # Schreibweise der Bildungsplan-Texte
        ("  l  mb ", "MB"),
        ("LFDB", "LFDB"),      # ⚠ beginnt mit L, ist aber selbst das Kürzel
        ("", ""),
        (None, ""),
    ],
)
def test_lp_kuerzel_normalisierung(eingabe, erwartet):
    assert normalize_lp_code(eingabe) == erwartet


def test_lfdb_wird_nicht_verstuemmelt():
    """Das Leerzeichen im Muster ist der ganze Punkt.

    Ohne es würde aus `LFDB` (Leitfaden Demokratiebildung) ein `FDB` — ein Kürzel, das
    es nicht gibt, und der Verweis liefe künftig ins Leere.
    """
    assert normalize_lp_code("LFDB") == "LFDB"
    assert leitperspektive_code({"bp_id": "BP2016BW_ALLG_LP_LFDB"}) == "LFDB"


@pytest.mark.parametrize(
    "metadata,erwartet",
    [
        ({"bp_id": "BP2016BW_ALLG_LP_PG"}, "PG"),          # der reale Fall: kein code
        ({"code": "BO", "bp_id": "BP2016BW_ALLG_LP_BO"}, "BO"),
        ({"code": "L BO"}, "BO"),                           # code gesetzt, aber unsauber
        ({"bp_id": "BP2016BW_ALLG_GYM_M_IK_5-6_01"}, ""),   # kein LP-Knoten
        ({}, ""),
        (None, ""),
    ],
)
def test_lp_kuerzel_aus_metadaten(metadata, erwartet):
    assert leitperspektive_code(metadata) == erwartet
