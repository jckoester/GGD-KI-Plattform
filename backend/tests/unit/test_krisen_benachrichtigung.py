"""Die Benachrichtigung über Krisenfälle (AP2).

Zwei Zusagen: Sie sagt **dass** etwas zu tun ist, nicht **was** passiert ist — und
sie überschwemmt niemanden.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.crisis import benachrichtigung as b
from app.mail.sender import Versandergebnis

JETZT = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


class TestText:

    def test_nennt_zahl_und_weg(self):
        text = b.text(offen=3, aelteste_tage=5)
        assert "3" in text
        assert "5 Tagen" in text
        assert "/flags" in text

    def test_kann_gar_nichts_verraten(self):
        """Die stärkere Zusage: Der Text **bekommt** nichts Verräterisches.

        Eine Wortsuche im Ergebnis wäre die schwächere Prüfung — und sie stolperte
        prompt über den eigenen Erklärsatz („weder Person noch Kategorie noch
        Inhalt"). Was zählt, ist die Signatur: zwei Zahlen, sonst nichts. Wer hier
        Kategorie oder Pseudonym ergänzt, bricht diesen Test.
        """
        import inspect
        parameter = list(inspect.signature(b.text).parameters)
        assert parameter == ["offen", "aelteste_tage"]

    def test_keine_kategorie_aus_der_konfiguration_taucht_auf(self):
        """Gegenprobe am echten Bestand — die Signatur allein prüft nur die Absicht."""
        from app.crisis.config import load_crisis_triggers

        text = b.text(offen=1, aelteste_tage=0).lower()
        for regel in load_crisis_triggers().triggers:
            assert regel.category.lower() not in text, regel.category

    def test_sagt_ausdruecklich_was_fehlt(self):
        # Sonst liest sich die Kargheit wie ein Versehen.
        text = b.text(offen=1, aelteste_tage=None)
        assert "weder Person noch Kategorie noch Inhalt" in text

    def test_heute_eingegangen_statt_null_tage(self):
        assert "heute eingegangen" in b.text(offen=1, aelteste_tage=0)

    def test_ohne_offenen_fall_kein_altersangabe(self):
        text = b.text(offen=0, aelteste_tage=None)
        assert "Ältester" not in text


class _Sitzung:
    def __init__(self, werte):
        self._werte = list(werte)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, *a, **kw):
        return self._werte.pop(0)


def _factory(im_fenster, offen, aeltestes):
    return lambda: _Sitzung([im_fenster, offen, aeltestes])


class TestDaempfung:

    @pytest.mark.asyncio
    async def test_das_erste_flag_im_fenster_verschickt(self, monkeypatch):
        monkeypatch.setattr(settings, "crisis_notify_to", ["a@example.org"])
        versendet = []

        async def sender(betreff, text, empfaenger):
            versendet.append(betreff)
            return Versandergebnis(True)

        ok = await b.benachrichtige(
            _factory(1, 1, JETZT), sender=sender, jetzt=JETZT
        )
        assert ok is True and len(versendet) == 1

    @pytest.mark.asyncio
    async def test_weitere_flags_im_fenster_schweigen(self, monkeypatch):
        """Eine Klasse, die dasselbe Wort ausprobiert, löst zwanzig Flags aus —
        die einundzwanzigste Mail liest niemand mehr."""
        monkeypatch.setattr(settings, "crisis_notify_to", ["a@example.org"])
        versendet = []

        async def sender(betreff, text, empfaenger):
            versendet.append(betreff)
            return Versandergebnis(True)

        ok = await b.benachrichtige(
            _factory(7, 7, JETZT), sender=sender, jetzt=JETZT
        )
        assert ok is False and versendet == []

    @pytest.mark.asyncio
    async def test_die_daempfung_braucht_keinen_gemerkten_zustand(self):
        """Sie zählt die Flags im Fenster — neustartfest und über Prozesse hinweg.

        Ein gemerkter „letzter Versand" läge im Arbeitsspeicher: weg beim Neustart,
        je Arbeitsprozess ein eigener.
        """
        import inspect
        quelle = inspect.getsource(b)
        assert "global " not in quelle


class TestInhaltDerLage:

    @pytest.mark.asyncio
    async def test_alter_des_aeltesten_faelle_wird_berechnet(self, monkeypatch):
        monkeypatch.setattr(settings, "crisis_notify_to", ["a@example.org"])
        gesendet = {}

        async def sender(betreff, text, empfaenger):
            gesendet["text"] = text
            return Versandergebnis(True)

        await b.benachrichtige(
            _factory(1, 4, JETZT - timedelta(days=12)), sender=sender, jetzt=JETZT
        )
        assert "12 Tagen" in gesendet["text"]
        assert "4" in gesendet["text"]

    @pytest.mark.asyncio
    async def test_zeitzonenlose_zeitstempel_kippen_die_rechnung_nicht(self, monkeypatch):
        """Postgres kann `timestamp without time zone` liefern — dann scheitert die
        Subtraktion, und die Benachrichtigung ginge gar nicht raus."""
        monkeypatch.setattr(settings, "crisis_notify_to", ["a@example.org"])
        gesendet = {}

        async def sender(betreff, text, empfaenger):
            gesendet["text"] = text
            return Versandergebnis(True)

        naiv = (JETZT - timedelta(days=3)).replace(tzinfo=None)
        await b.benachrichtige(_factory(1, 1, naiv), sender=sender, jetzt=JETZT)
        assert "3 Tagen" in gesendet["text"]


# ── Einsicht-Anträge ────────────────────────────────────────────────────────────


def _antrags_factory(wartend):
    return lambda: _Sitzung([wartend])


class TestAntragstext:

    def test_nennt_zahl_und_weg_zur_freigabe(self):
        text = b.antragstext(wartend=2)
        assert "2" in text
        assert "/review" in text

    def test_kann_gar_nichts_verraten(self):
        """Wie bei `text`: geprüft wird die **Signatur**, nicht der Wortlaut.

        Wer hier `requested_by` oder die Kategorie ergänzt, bricht diesen Test —
        und genau das soll er. Eine Wortsuche im Ergebnis stolperte über den
        eigenen Erklärsatz.
        """
        import inspect
        assert list(inspect.signature(b.antragstext).parameters) == ["wartend"]

    def test_keine_kategorie_aus_der_konfiguration_taucht_auf(self):
        from app.crisis.config import load_crisis_triggers

        text = b.antragstext(wartend=1).lower()
        for regel in load_crisis_triggers().triggers:
            assert regel.category.lower() not in text, regel.category

    def test_sagt_ausdruecklich_was_fehlt(self):
        assert "weder die antragstellende Person noch den Fall" in b.antragstext(1)


class TestAntragsbenachrichtigung:

    @pytest.mark.asyncio
    async def test_geht_an_die_review_liste_nicht_an_die_flag_liste(self, monkeypatch):
        """Die Zusage, an der alles hängt.

        Antrag und Zweitfreigabe im selben Postfach machen aus dem
        Vier-Augen-Prinzip (ADR-008 Teil 6) zwei Klicks derselben Person. Ein
        Rückfall auf `crisis_notify_to`, wenn die review-Liste leer ist, wäre
        deshalb bequem und falsch — er stünde nirgends und fiele niemandem auf.
        """
        monkeypatch.setattr(settings, "crisis_notify_to", ["flags@example.org"])
        monkeypatch.setattr(settings, "crisis_review_notify_to", ["review@example.org"])
        gesehen = {}

        async def sender(betreff, text, empfaenger):
            gesehen["empfaenger"] = empfaenger
            return Versandergebnis(True)

        ok = await b.benachrichtige_antrag(_antrags_factory(1), sender=sender)
        assert ok is True
        assert gesehen["empfaenger"] == ["review@example.org"]
        assert "flags@example.org" not in gesehen["empfaenger"]

    @pytest.mark.asyncio
    async def test_leere_review_liste_faellt_nicht_auf_die_flag_liste_zurueck(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "crisis_notify_to", ["flags@example.org"])
        monkeypatch.setattr(settings, "crisis_review_notify_to", [])
        gesehen = {}

        async def sender(betreff, text, empfaenger):
            gesehen["empfaenger"] = empfaenger
            return Versandergebnis(False, "keine Empfänger")

        await b.benachrichtige_antrag(_antrags_factory(1), sender=sender)
        assert gesehen["empfaenger"] == []

    @pytest.mark.asyncio
    async def test_jeder_antrag_verschickt_keine_daempfung(self, monkeypatch):
        """Anders als bei Flags kann es hier keine Flut geben.

        Je Flag lässt `create_access_request` nur **einen** aktiven Antrag zu (sonst
        409), und beantragen darf allein die Admin-Rolle. Eine Dämpfung verschluckte
        hier echte Fälle, statt Lärm zu vermeiden.
        """
        monkeypatch.setattr(settings, "crisis_review_notify_to", ["r@example.org"])
        versendet = []

        async def sender(betreff, text, empfaenger):
            versendet.append(betreff)
            return Versandergebnis(True)

        for wartend in (1, 2, 3):
            await b.benachrichtige_antrag(_antrags_factory(wartend), sender=sender)
        assert len(versendet) == 3
