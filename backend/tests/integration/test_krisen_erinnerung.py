"""Erinnerung und Aufbewahrungs-Obergrenze für Krisenfälle (AP3).

Zwei Zusagen, beide gegen echtes Postgres geprüft, weil sie in SQL-Bedingungen
stecken:

* An einen unerledigten Fall wird erinnert — aber nicht täglich.
* Ein offenes Flag schützt die Konversation **nicht mehr unbefristet** — und der
  Schutz endet nur, wenn vorher erinnert wurde.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.crisis import erinnerung
from app.crons.cleanup_service import _protecting_flag_condition
from app.db.models import (
    Conversation,
    ConversationAccessRequest,
    ConversationFlag,
    Message,
)
from app.mail.sender import Versandergebnis
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio

JETZT = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)


async def _sender_sammler(gesendet):
    async def sender(betreff, text, empfaenger):
        gesendet.append((betreff, text))
        return Versandergebnis(True)
    return sender


@pytest_asyncio.fixture
async def welt(async_engine):
    """Vier Fälle mit unterschiedlichem Alter und Erinnerungsstand."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    ids = {}
    async with factory() as s:
        conv = Conversation(id=uuid4(), pseudonym=TEACHER1_PSEUDO, model_used="gpt-4o")
        s.add(conv)
        await s.flush()

        faelle = {
            # frisch: noch nicht erinnerungsreif
            "frisch": (JETZT - timedelta(days=2), None, "open"),
            # überfällig, nie erinnert
            "ueberfaellig": (JETZT - timedelta(days=30), None, "open"),
            # überfällig, aber gestern erinnert
            "gestern_erinnert": (JETZT - timedelta(days=30), JETZT - timedelta(days=1), "open"),
            # kurz vor der Grenze (365 - 14 = 351 Tage)
            "vor_grenze": (JETZT - timedelta(days=360), JETZT - timedelta(days=1), "open"),
            # über der Grenze, erinnert → Schutz endet
            "ueber_grenze": (JETZT - timedelta(days=400), JETZT - timedelta(days=10), "open"),
            # über der Grenze, aber nie erinnert → bleibt geschützt
            "nie_erinnert": (JETZT - timedelta(days=400), None, "open"),
        }
        for name, (flagged, erinnert, status) in faelle.items():
            flag = ConversationFlag(
                id=uuid4(), conversation_id=conv.id, flag_source="auto_crisis",
                flag_category="test", severity="alert", status=status,
                flagged_at=flagged, last_reminder_at=erinnert,
            )
            s.add(flag)
            await s.flush()
            ids[name] = flag.id
        await s.commit()
        ids["conversation"] = conv.id

    yield ids

    async with factory() as s:
        await s.execute(delete(ConversationAccessRequest).where(
            ConversationAccessRequest.conversation_id == ids["conversation"]))
        await s.execute(delete(ConversationFlag).where(
            ConversationFlag.conversation_id == ids["conversation"]))
        await s.execute(delete(Message).where(
            Message.conversation_id == ids["conversation"]))
        await s.execute(delete(Conversation).where(
            Conversation.id == ids["conversation"]))
        await s.commit()


@pytest_asyncio.fixture
async def antraege(async_engine, welt):
    """Drei wartende Einsicht-Anträge mit unterschiedlichem Erinnerungsstand.

    Hängen an den Flags aus `welt`, weil `flag_id` ein Fremdschlüssel ist. Die
    Aufräumung erledigt `welt` mit — deshalb hier kein eigenes Löschen.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    ids = {}
    async with factory() as s:
        faelle = {
            # frisch gestellt: noch nicht erinnerungsreif
            "frisch": (welt["frisch"], JETZT - timedelta(days=1), None),
            # liegt seit vier Wochen, nie erinnert
            "ueberfaellig": (welt["ueberfaellig"], JETZT - timedelta(days=28), None),
            # überfällig, aber gestern erinnert → ruht
            "gestern_erinnert": (
                welt["gestern_erinnert"], JETZT - timedelta(days=28),
                JETZT - timedelta(days=1),
            ),
        }
        for name, (flag_id, gestellt, erinnert) in faelle.items():
            req = ConversationAccessRequest(
                id=uuid4(), conversation_id=welt["conversation"], flag_id=flag_id,
                requested_by="admin-pseudo", status="pending",
                requested_at=gestellt, last_reminder_at=erinnert,
            )
            s.add(req)
            await s.flush()
            ids[name] = req.id
        await s.commit()

    return ids


class TestErinnerung:

    async def test_ueberfaellige_faelle_loesen_eine_erinnerung_aus(self, async_engine, welt):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        gesendet = []
        lage = await erinnerung.lauf(
            factory, sender=await _sender_sammler(gesendet), jetzt=JETZT
        )
        assert lage.faellig >= 1
        betreffe = [b for b, _ in gesendet]
        assert erinnerung.BETREFF_ERINNERUNG in betreffe

    async def test_eine_sammelmail_statt_einer_je_fall(self, async_engine, welt):
        """Zwanzig Einzelmails an dasselbe Postfach sind keine zwanzigfache
        Aufmerksamkeit, sondern gar keine."""
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        gesendet = []
        await erinnerung.lauf(factory, sender=await _sender_sammler(gesendet), jetzt=JETZT)
        erinnerungen = [b for b, _ in gesendet if b == erinnerung.BETREFF_ERINNERUNG]
        assert len(erinnerungen) == 1

    async def test_gestern_erinnerte_faelle_ruhen(self, async_engine, welt):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            lage = await erinnerung.lage_ermitteln(db, JETZT)
        # `ueberfaellig` und `nie_erinnert` sind reif, `gestern_erinnert` nicht.
        assert lage.faellig >= 1
        async with factory() as db:
            reif = await db.scalar(
                select(ConversationFlag.last_reminder_at)
                .where(ConversationFlag.id == welt["gestern_erinnert"])
            )
        assert reif is not None

    async def test_der_lauf_vermerkt_die_erinnerung(self, async_engine, welt):
        """Ohne den Vermerk käme morgen dieselbe Liste — und die Löschfrist startete nie."""
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        await erinnerung.lauf(factory, sender=await _sender_sammler([]), jetzt=JETZT)
        async with factory() as db:
            vermerk = await db.scalar(
                select(ConversationFlag.last_reminder_at)
                .where(ConversationFlag.id == welt["ueberfaellig"])
            )
        assert vermerk is not None

    async def test_letzte_warnung_bei_naher_grenze(self, async_engine, welt):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        gesendet = []
        lage = await erinnerung.lauf(
            factory, sender=await _sender_sammler(gesendet), jetzt=JETZT
        )
        assert lage.vor_loeschung >= 1
        warnungen = [t for b, t in gesendet if b == erinnerung.BETREFF_WARNUNG]
        assert warnungen, "keine letzte Warnung versendet"
        # Eine Warnung, die die Folge verschweigt, ist keine.
        assert "gelöscht" in warnungen[0]


class TestObergrenze:

    async def _geschuetzt(self, async_engine, flag_id) -> bool:
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            treffer = await db.scalar(
                select(ConversationFlag.id).where(
                    ConversationFlag.id == flag_id,
                    _protecting_flag_condition(JETZT),
                )
            )
        return treffer is not None

    async def test_junges_offenes_flag_schuetzt(self, async_engine, welt):
        assert await self._geschuetzt(async_engine, welt["frisch"]) is True

    async def test_altes_erinnertes_flag_schuetzt_nicht_mehr(self, async_engine, welt):
        """Der eigentliche Punkt: Vorher galt der Schutz unbefristet."""
        assert await self._geschuetzt(async_engine, welt["ueber_grenze"]) is False

    async def test_altes_flag_ohne_erinnerung_bleibt_geschuetzt(self, async_engine, welt):
        """Nie gewarnt heißt: nicht löschen. Läuft der Erinnerungslauf nicht,
        bleibt alles liegen — die sichere Richtung."""
        assert await self._geschuetzt(async_engine, welt["nie_erinnert"]) is True

    async def test_knapp_vor_der_grenze_schuetzt_noch(self, async_engine, welt):
        assert await self._geschuetzt(async_engine, welt["vor_grenze"]) is True


class TestWartendeAntraege:
    """Ein Antrag auf Einsicht blockiert die Bearbeitung, solange niemand freigibt.

    Bis 10.09.2026 erfuhren die `review`-Personen davon nur über den Zähler am
    Avatar — den sieht, wer sich anmeldet.
    """

    async def test_ueberfaelliger_antrag_loest_eine_erinnerung_aus(
        self, async_engine, welt, antraege
    ):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        gesendet = []
        lage = await erinnerung.lauf(
            factory, sender=await _sender_sammler(gesendet), jetzt=JETZT
        )
        assert lage.antraege_faellig >= 1
        assert lage.antraege_gesamt == 3
        assert erinnerung.BETREFF_ANTRAEGE in [b for b, _ in gesendet]

    async def test_gestern_erinnerter_antrag_ruht(self, async_engine, welt, antraege):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        await erinnerung.lauf(factory, sender=await _sender_sammler([]), jetzt=JETZT)
        async with factory() as db:
            vermerk = await db.scalar(
                select(ConversationAccessRequest.last_reminder_at)
                .where(ConversationAccessRequest.id == antraege["gestern_erinnert"])
            )
        # Unverändert — der Lauf hat ihn nicht angefasst.
        assert vermerk == JETZT - timedelta(days=1)

    async def test_frischer_antrag_wird_nicht_gemahnt(self, async_engine, welt, antraege):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        await erinnerung.lauf(factory, sender=await _sender_sammler([]), jetzt=JETZT)
        async with factory() as db:
            vermerk = await db.scalar(
                select(ConversationAccessRequest.last_reminder_at)
                .where(ConversationAccessRequest.id == antraege["frisch"])
            )
        assert vermerk is None

    async def test_der_lauf_vermerkt_die_antragserinnerung(
        self, async_engine, welt, antraege
    ):
        """Ohne den Vermerk käme morgen dieselbe Mahnung — täglich, wochenlang."""
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        await erinnerung.lauf(factory, sender=await _sender_sammler([]), jetzt=JETZT)
        async with factory() as db:
            vermerk = await db.scalar(
                select(ConversationAccessRequest.last_reminder_at)
                .where(ConversationAccessRequest.id == antraege["ueberfaellig"])
            )
        assert vermerk is not None

    async def test_der_zweite_lauf_am_selben_tag_schweigt(
        self, async_engine, welt, antraege
    ):
        """Die eigentliche Wirkung der Spalte, an zwei Läufen nachgestellt."""
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        erster, zweiter = [], []
        await erinnerung.lauf(factory, sender=await _sender_sammler(erster), jetzt=JETZT)
        await erinnerung.lauf(factory, sender=await _sender_sammler(zweiter), jetzt=JETZT)

        assert erinnerung.BETREFF_ANTRAEGE in [b for b, _ in erster]
        assert erinnerung.BETREFF_ANTRAEGE not in [b for b, _ in zweiter]

    async def test_antragsmail_geht_an_die_review_liste(
        self, async_engine, welt, antraege, monkeypatch
    ):
        """Die Trennung, die das Vier-Augen-Prinzip trägt — hier im echten Lauf.

        Der Unit-Test prüft dasselbe an `benachrichtige_antrag`; hier zählt, dass
        der Cron nicht versehentlich `empfaenger` aus der Flag-Zeile weiterreicht.
        """
        monkeypatch.setattr(settings, "crisis_notify_to", ["flags@example.org"])
        monkeypatch.setattr(settings, "crisis_review_notify_to", ["review@example.org"])
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        nach_betreff = {}

        async def sender(betreff, text, empfaenger):
            nach_betreff[betreff] = empfaenger
            return Versandergebnis(True)

        await erinnerung.lauf(factory, sender=sender, jetzt=JETZT)

        assert nach_betreff[erinnerung.BETREFF_ANTRAEGE] == ["review@example.org"]
        assert nach_betreff[erinnerung.BETREFF_ERINNERUNG] == ["flags@example.org"]

    async def test_der_text_nennt_zahl_und_weg_zur_freigabe(
        self, async_engine, welt, antraege
    ):
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        gesendet = []
        await erinnerung.lauf(factory, sender=await _sender_sammler(gesendet), jetzt=JETZT)
        texte = [t for b, t in gesendet if b == erinnerung.BETREFF_ANTRAEGE]
        assert texte, "keine Antragserinnerung versendet"
        assert "/review" in texte[0]
        assert "28 Tagen" in texte[0]  # ältester wartender Antrag

    async def test_probelauf_vermerkt_auch_bei_antraegen_nichts(
        self, async_engine, welt, antraege, monkeypatch
    ):
        """`--dry-run` legt **beide** Vermerk-Funktionen still.

        Seit Migration 0060 gibt es zwei. Wer nur `_vermerke` ersetzt, schiebt mit
        einem Probelauf still die Antrags-Erinnerung um eine Woche nach hinten — ein
        Trockenlauf, der etwas verändert, ist keiner. Der Test stellt genau das
        Vorgehen des Skripts nach.
        """
        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

        async def _kein_vermerk(db, _jetzt):
            return 0

        monkeypatch.setattr(erinnerung, "_vermerke", _kein_vermerk)
        monkeypatch.setattr(erinnerung, "_vermerke_antraege", _kein_vermerk)
        await erinnerung.lauf(factory, sender=await _sender_sammler([]), jetzt=JETZT)

        async with factory() as db:
            antrag = await db.scalar(
                select(ConversationAccessRequest.last_reminder_at)
                .where(ConversationAccessRequest.id == antraege["ueberfaellig"])
            )
            flag = await db.scalar(
                select(ConversationFlag.last_reminder_at)
                .where(ConversationFlag.id == welt["ueberfaellig"])
            )
        assert antrag is None
        assert flag is None
