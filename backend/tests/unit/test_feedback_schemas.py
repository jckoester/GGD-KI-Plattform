"""Was der Client schickt, bevor die Datenbank es sieht (ADR-020, AP2).

Die Trennlinie, um die es hier geht: **Getipptes wird geprüft, Beigelegtes gekürzt.**
Eine zu kurze Meldung ist eine Aussage über die Meldung und gehört abgewiesen; eine
überlange Browserkennung ist eine Eigenheit des Browsers und darf keinen Fehlerbericht
verhindern.
"""
import pytest
from pydantic import ValidationError

from app.feedback.schemas import (
    MAX_LAENGE,
    MAX_ROUTE,
    MAX_USER_AGENT,
    MIN_LAENGE,
    FeedbackCreate,
)


def _felder(**abweichend):
    basis = {"category": "bug", "content": "x" * 25, "app_version": "0.10.3"}
    basis.update(abweichend)
    return basis


class TestText:
    def test_gueltige_meldung(self):
        daten = FeedbackCreate(**_felder())
        assert daten.category == "bug"
        assert daten.contact is None
        assert daten.attach_conversation_id is None

    def test_zu_kurz_wird_abgewiesen(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(**_felder(content="x" * (MIN_LAENGE - 1)))

    def test_genau_die_mindestlaenge_geht(self):
        assert len(FeedbackCreate(**_felder(content="x" * MIN_LAENGE)).content) == MIN_LAENGE

    def test_leerzeichen_zaehlen_nicht_als_text(self):
        """Sonst käme „test" mit angehängten Leerzeichen durch die Mindestlänge."""
        with pytest.raises(ValidationError):
            FeedbackCreate(**_felder(content="test" + " " * 40))

    def test_randleerzeichen_fallen_weg(self):
        daten = FeedbackCreate(**_felder(content="  " + "x" * 25 + "\n"))
        assert daten.content == "x" * 25

    def test_zu_lang_wird_abgewiesen(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(**_felder(content="x" * (MAX_LAENGE + 1)))

    def test_unbekannte_kategorie(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(**_felder(category="frage"))


class TestKontakt:
    def test_leeres_feld_wird_none(self):
        """`""` in der Spalte sähe für die Sichtung aus wie eine Angabe."""
        assert FeedbackCreate(**_felder(contact="   ")).contact is None

    def test_angabe_wird_entrandet(self):
        assert FeedbackCreate(**_felder(contact=" Jan, 10b ")).contact == "Jan, 10b"

    def test_zu_lange_angabe_wird_abgewiesen(self):
        """Getipptes, also geprüft — anders als die automatischen Felder unten."""
        with pytest.raises(ValidationError):
            FeedbackCreate(**_felder(contact="x" * 201))


class TestAutomatischerKontext:
    def test_route_verliert_die_query(self):
        """Eine Query kann tragen, was in einer Meldung nichts zu suchen hat."""
        daten = FeedbackCreate(**_felder(route="/knowledge/search?q=Krankheit+von+Mia"))
        assert daten.route == "/knowledge/search"

    def test_route_verliert_das_fragment(self):
        assert FeedbackCreate(**_felder(route="/help/chat#mathe")).route == "/help/chat"

    def test_lange_route_wird_gekuerzt_statt_abgewiesen(self):
        daten = FeedbackCreate(**_felder(route="/x" * 300))
        assert len(daten.route) == MAX_ROUTE

    def test_lange_browserkennung_wird_gekuerzt_statt_abgewiesen(self):
        """Der Bericht ist das Wertvolle, die Kennung die Zugabe."""
        daten = FeedbackCreate(**_felder(user_agent="Mozilla/5.0 " * 200))
        assert len(daten.user_agent) == MAX_USER_AGENT

    def test_viewport_wird_gekuerzt(self):
        assert len(FeedbackCreate(**_felder(viewport="3" * 99)).viewport) == 20

    def test_leere_route_wird_none(self):
        assert FeedbackCreate(**_felder(route="")).route is None

    def test_version_ist_pflicht(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(category="bug", content="x" * 25)
