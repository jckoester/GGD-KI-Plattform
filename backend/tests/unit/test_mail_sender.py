"""Der Mailversand (AP1 des Krisen-Benachrichtigungs-Plans).

Geprüft wird alles außer dem Versand selbst: Wen die Nachricht erreicht, was sie
trägt, und dass ein Fehlschlag nichts mitreißt. Ob die Schul-SMTP sie annimmt,
zeigt erst der Produktivbetrieb.
"""
import logging
from email.message import EmailMessage

import pytest

from app.config import settings
from app.mail import sender


@pytest.fixture
def konfiguriert(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
    monkeypatch.setattr(settings, "smtp_from", "ki@example.org")
    monkeypatch.setattr(settings, "smtp_user", "")
    monkeypatch.setattr(settings, "smtp_password", "")


class TestOhneKonfiguration:

    @pytest.mark.asyncio
    async def test_versendet_nichts_und_wirft_nicht(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "smtp_host", "")
        monkeypatch.setattr(settings, "smtp_from", "")

        with caplog.at_level(logging.WARNING, logger="app.mail.sender"):
            ergebnis = await sender.sende("Betreff", "Text", ["a@example.org"])

        assert ergebnis.versendet is False
        assert ergebnis.grund == "nicht konfiguriert"

    @pytest.mark.asyncio
    async def test_der_inhalt_landet_im_log(self, monkeypatch, caplog):
        """Sonst verschwände eine Krisen-Benachrichtigung spurlos."""
        monkeypatch.setattr(settings, "smtp_host", "")
        monkeypatch.setattr(settings, "smtp_from", "")

        with caplog.at_level(logging.WARNING, logger="app.mail.sender"):
            await sender.sende("Neuer Fall", "Es liegen 3 Fälle vor.", ["a@example.org"])

        gesamt = " ".join(r.getMessage() for r in caplog.records)
        assert "Es liegen 3 Fälle vor." in gesamt

    @pytest.mark.asyncio
    async def test_meldet_sich_als_warnung_nicht_als_debug(self, monkeypatch, caplog):
        # Im Produktivsystem ist fehlendes SMTP ein Befund, keine Nebensache.
        monkeypatch.setattr(settings, "smtp_host", "")
        monkeypatch.setattr(settings, "smtp_from", "")
        with caplog.at_level(logging.DEBUG, logger="app.mail.sender"):
            await sender.sende("B", "T", ["a@example.org"])
        assert any(r.levelname == "WARNING" for r in caplog.records)


class TestEmpfaenger:

    @pytest.mark.asyncio
    async def test_ohne_empfaenger_wird_nicht_versendet(self, konfiguriert):
        ergebnis = await sender.sende("B", "T", [])
        assert ergebnis.versendet is False
        assert ergebnis.grund == "keine Empfänger"

    def test_empfaenger_stehen_in_bcc(self, konfiguriert):
        """Wer eine solche Mail weiterleitet, gäbe sonst mit, wer sonst zuständig ist."""
        msg = sender._nachricht("B", "T", ["a@example.org", "b@example.org"])
        assert msg["Bcc"] == "a@example.org, b@example.org"
        assert "a@example.org" not in (msg["To"] or "")

    def test_automatische_antworten_werden_unterdrueckt(self, konfiguriert):
        # Ein Postfach mit Urlaubsschaltung antwortete sonst auf jede Erinnerung.
        msg = sender._nachricht("B", "T", ["a@example.org"])
        assert msg["Auto-Submitted"] == "auto-generated"

    def test_betreff_und_text_kommen_an(self, konfiguriert):
        msg = sender._nachricht("Neuer Fall", "Zeile eins", ["a@example.org"])
        assert msg["Subject"] == "Neuer Fall"
        assert "Zeile eins" in msg.get_content()


class TestVersand:

    @pytest.mark.asyncio
    async def test_erfolgreicher_versand(self, konfiguriert, monkeypatch):
        versendet: list[EmailMessage] = []
        monkeypatch.setattr(sender, "_versende_blockierend", versendet.append)

        ergebnis = await sender.sende("B", "T", ["a@example.org"])

        assert ergebnis.versendet is True
        assert len(versendet) == 1

    @pytest.mark.asyncio
    async def test_fehlschlag_wirft_nicht(self, konfiguriert, monkeypatch, caplog):
        """Der Aufrufer ist nie der Nutzer — ein Chat darf daran nicht scheitern."""
        def kaputt(msg):
            raise OSError("Verbindung abgelehnt")

        monkeypatch.setattr(sender, "_versende_blockierend", kaputt)

        with caplog.at_level(logging.ERROR, logger="app.mail.sender"):
            ergebnis = await sender.sende("B", "T", ["a@example.org"])

        assert ergebnis.versendet is False
        assert "Verbindung abgelehnt" in (ergebnis.grund or "")


class TestStartpruefung:

    def test_halbe_konfiguration_meldet_sich(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "smtp_host", "mail.example.org")
        monkeypatch.setattr(settings, "smtp_from", "")
        with caplog.at_level(logging.ERROR, logger="app.mail.sender"):
            sender.pruefe_beim_start()
        assert any("SMTP_FROM" in r.getMessage() for r in caplog.records)

    def test_gar_keine_konfiguration_ist_kein_fehler(self, monkeypatch, caplog):
        # Die Entwicklungsumgebung soll ohne Einrichtung laufen.
        monkeypatch.setattr(settings, "smtp_host", "")
        monkeypatch.setattr(settings, "smtp_from", "")
        with caplog.at_level(logging.DEBUG, logger="app.mail.sender"):
            sender.pruefe_beim_start()
        assert not [r for r in caplog.records if r.levelname == "ERROR"]

    def test_vollstaendige_konfiguration_schweigt(self, konfiguriert, caplog):
        with caplog.at_level(logging.DEBUG, logger="app.mail.sender"):
            sender.pruefe_beim_start()
        assert not [r for r in caplog.records if r.levelname in ("ERROR", "WARNING")]
