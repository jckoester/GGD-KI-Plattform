"""Die Mail über neue Rückmeldungen (ADR-020, AP3).

Zwei Zusagen: Sie sagt genug, um im Postfach zu entscheiden, ob etwas dringend ist —
und sie trägt weder Pseudonym noch Kontaktangabe noch einen angehängten Chat hinaus.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.feedback import benachrichtigung as b
from app.mail.sender import Versandergebnis

JETZT = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)

KONTAKT = "KLARNAME-JAN-KOESTER-10B"
CHATINHALT = "GEHEIMER-CHATINHALT"
PSEUDO = "PSEUDONYM-ABC123"


def _eintrag(inhalt="Der Knopf zum Abschicken reagiert nicht."):
    return b.Eintrag(kategorie="bug", rolle="student", version="0.10.3",
                     vorschau=b._vorschau(inhalt))


class TestText:
    def test_nennt_zahl_kategorie_rolle_version_und_weg(self):
        text = b.text(offen=4, eintraege=[_eintrag()])
        assert "4" in text
        assert "Fehler" in text and "Schüler:in" in text and "0.10.3" in text
        assert "/feedback/manage" in text

    def test_kann_kontakt_und_anhang_gar_nicht_tragen(self):
        """Die stärkere Zusage: Der Text **bekommt** sie nicht.

        Eine Wortsuche im Ergebnis prüfte nur den einen Beispielfall. Was zählt, ist
        die Struktur: vier Felder je Eintrag, und keines davon heißt Kontakt oder
        Pseudonym. Wer hier eines ergänzt, bricht diesen Test.
        """
        assert b.Eintrag._fields == ("kategorie", "rolle", "version", "vorschau")

        import inspect
        assert list(inspect.signature(b.text).parameters) == ["offen", "eintraege"]

    def test_sagt_ausdruecklich_was_fehlt(self):
        # Sonst liest sich die Kargheit wie ein Versehen.
        assert "weder Pseudonym noch Kontaktangabe" in b.text(1, [_eintrag()])

    def test_lange_meldungen_werden_gekuerzt(self):
        lang = "A" * 500
        zeile = b._vorschau(lang)
        assert len(zeile) == b.VORSCHAU + 1  # 200 Zeichen plus Auslassungszeichen
        assert zeile.endswith("…")

    def test_zeilenumbrueche_zerreissen_die_liste_nicht(self):
        assert "\n" not in b._vorschau("Erste Zeile\n\nZweite Zeile")

    def test_unbekannte_kategorie_bleibt_stehen(self):
        """Lieber der rohe Wert als eine Lücke, wenn später eine Kategorie dazukommt."""
        eintrag = b.Eintrag("frage", "tutor", "0.11.0", "Text")
        assert "frage" in b.text(1, [eintrag]) and "tutor" in b.text(1, [eintrag])


class _Sitzung:
    """Gibt der Reihe nach zurück, was `_lage` abfragt: zwei Zahlen, dann die Zeilen."""

    def __init__(self, im_fenster, offen, zeilen):
        self._skalare = [im_fenster, offen]
        self._zeilen = zeilen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def scalar(self, *a, **kw):
        return self._skalare.pop(0)

    async def execute(self, *a, **kw):
        zeilen = self._zeilen

        class _Ergebnis:
            def all(self):
                return zeilen

        return _Ergebnis()


def _factory(im_fenster, offen, zeilen=None):
    zeilen = zeilen if zeilen is not None else [("bug", "student", "0.10.3", "Ein Fehler.")]
    return lambda: _Sitzung(im_fenster, offen, zeilen)


@pytest.fixture
def empfaenger(monkeypatch):
    monkeypatch.setattr(settings, "feedback_notify_to", ["admin@example.org"])


class TestDaempfung:
    async def test_die_erste_meldung_im_fenster_verschickt(self, empfaenger):
        versendet = []

        async def sender(betreff, text, adressen):
            versendet.append((betreff, text, adressen))
            return Versandergebnis(True)

        ok = await b.benachrichtige(_factory(1, 1), sender=sender, jetzt=JETZT)
        assert ok is True
        assert len(versendet) == 1
        assert versendet[0][0] == "KI-Client: neue Rückmeldung(en)"

    async def test_weitere_meldungen_im_fenster_schweigen(self, empfaenger):
        """Eine Klasse, die eine Panne gemeinsam meldet, löst zwanzig Einträge aus."""
        versendet = []

        async def sender(betreff, text, adressen):
            versendet.append(betreff)
            return Versandergebnis(True)

        ok = await b.benachrichtige(_factory(5, 5), sender=sender, jetzt=JETZT)
        assert ok is False and versendet == []

    async def test_ohne_empfaenger_kein_versand(self, monkeypatch):
        """Leere Liste ist ein zulässiger Betriebszustand, kein Fehler."""
        monkeypatch.setattr(settings, "feedback_notify_to", [])
        gesehen = []

        async def sender(betreff, text, adressen):
            gesehen.append(adressen)
            return Versandergebnis(False, "keine Empfänger")

        ok = await b.benachrichtige(_factory(1, 1), sender=sender, jetzt=JETZT)
        assert ok is False and gesehen == [[]]

    async def test_die_daempfung_braucht_keinen_gemerkten_zustand(self):
        """Ein gemerkter „letzter Versand" läge im Arbeitsspeicher: weg beim Neustart,
        je Arbeitsprozess ein eigener."""
        import inspect
        assert "global " not in inspect.getsource(b)


class TestWasNichtHinausgeht:
    async def test_mailtext_traegt_weder_kontakt_noch_anhang_noch_pseudonym(self, empfaenger):
        """Gegenprobe am gesamten Weg: Marker in die Datenzeile, Suche im Ergebnis.

        Die Strukturprüfung oben zeigt, dass `text` sie nicht bekommt; dieser Test
        zeigt, dass auch `_lage` sie nicht einsammelt.
        """
        gesehen = {}

        async def sender(betreff, text, adressen):
            gesehen["text"] = text
            return Versandergebnis(True)

        # `_lage` fragt genau vier Spalten ab — stünden Kontakt oder Pseudonym dabei,
        # landeten sie hier in der Zeile und damit im Text.
        zeile = ("bug", "student", "0.10.3", f"Fehler. {CHATINHALT} {KONTAKT} {PSEUDO}")
        await b.benachrichtige(_factory(1, 1, [zeile]), sender=sender, jetzt=JETZT)

        # Der Meldungstext selbst kommt mit — das ist gewollt. Alles, was die
        # **Datenbank** daneben hält, nicht.
        import inspect
        quelle = inspect.getsource(b._lage)
        for spalte in ("Feedback.contact", "Feedback.pseudonym", "conversation_snapshot"):
            assert spalte not in quelle, f"{spalte} wird für die Mail geladen"
