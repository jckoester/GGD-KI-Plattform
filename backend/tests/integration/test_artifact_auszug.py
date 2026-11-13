"""Fach der Werkstatt-Produkte (0.41, Päckchen AN, Schritt 1; Alembic 0103).

Seit 0.41 trägt ein Produkt ein **eigenes** Fach. Beim Speichern aus dem Chat wird es kopiert —
aus der Konversation, sonst aus deren Gruppe. Bis 0.40 kam der Bezug allein über den
Herkunfts-Chat und fiel mit ihm weg (spätestens nach 93 Tagen). Diese Tests halten fest:

* Der Fachauszug liest die eigene Spalte; das Fach überlebt das Löschen des Chats.
* Die Gruppe zeigt die Produkte **ihres Fachs** (Plan F3 a) — eine Gruppe ohne Fach nichts.
* Der Eigentümerfilter steht davor: Fremde Produkte bleiben unsichtbar.
* Die Herkunft kommt vom Backend und nur aus **eigenen** Konversationen.
* Die Vorbelegung der Migration füllt Fach und Assistent aus der noch lebenden Konversation.

Gegen echtes Postgres, nicht gegen Mocks: Geprüft wird die Form der Abfragen.
"""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa

from app.artifacts import promote, store
from app.db.models import Artifact, Assistant, Conversation, Group, Message, Subject

ICH = "an1-ich"
FREMD = "an1-fremd"

# Feste Zeitpunkte statt `now()`: Die Reihenfolge der Ergebnisse ist Teil der Zusage.
T0 = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)


async def _fach(db, name: str) -> int:
    subject = Subject(name=name, slug=f"{name.lower()}-an1")
    db.add(subject)
    await db.flush()
    return subject.id


async def _gruppe(db, name: str, subject_id: int | None) -> int:
    gruppe = Group(name=name, slug=f"{name.lower()}-an1", type="teaching_group",
                   subject_id=subject_id)
    db.add(gruppe)
    await db.flush()
    return gruppe.id


async def _chat(db, pseudonym: str, subject_id=None, group_id=None, assistant_id=None):
    conv = Conversation(id=uuid4(), pseudonym=pseudonym, model_used="gpt-4o",
                        subject_id=subject_id, group_id=group_id, assistant_id=assistant_id)
    db.add(conv)
    await db.flush()
    return conv


async def _artefakt(db, owner: str, titel: str, *, fach=None, chat=None, versatz_min=0):
    art = Artifact(
        id=uuid4(), owner_pseudonym=owner, kind="document",
        mime_type="text/markdown", byte_size=10, title=titel,
        subject_id=fach, origin_conversation_id=chat.id if chat else None,
        created_at=T0 + timedelta(minutes=versatz_min),
        expires_at=T0 + timedelta(days=365),
    )
    db.add(art)
    await db.flush()
    return art


# ── Auszug ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fachauszug_liest_die_eigene_spalte(db_session):
    fach = await _fach(db_session, "AN1Deutsch")
    anderes = await _fach(db_session, "AN1Chemie")
    await _artefakt(db_session, ICH, "älter", fach=fach, versatz_min=0)
    await _artefakt(db_session, ICH, "neuer", fach=fach, versatz_min=5)
    await _artefakt(db_session, ICH, "anderes Fach", fach=anderes)
    await _artefakt(db_session, ICH, "ohne Fach")

    treffer = await store.list_artifacts(db_session, ICH, subject_id=fach)

    # Neueste zuerst — die Reihenfolge ist Teil der Zusage, nicht Zufall.
    assert [a.title for a in treffer] == ["neuer", "älter"]


@pytest.mark.asyncio
async def test_gruppe_zeigt_die_produkte_ihres_fachs(db_session):
    """F3 (a): Zwei Gruppen im selben Fach zeigen dasselbe — das Produkt gehört keiner Gruppe."""
    fach = await _fach(db_session, "AN1Mathe")
    gruppe_a = await _gruppe(db_session, "AN1A", fach)
    gruppe_b = await _gruppe(db_session, "AN1B", fach)
    ohne_fach = await _gruppe(db_session, "AN1AG", None)
    await _artefakt(db_session, ICH, "Mathe", fach=fach)
    await _artefakt(db_session, ICH, "ohne Fach")

    for gruppe in (gruppe_a, gruppe_b):
        assert [a.title for a in await store.list_artifacts(db_session, ICH, group_id=gruppe)] == ["Mathe"]
    assert await store.list_artifacts(db_session, ICH, group_id=ohne_fach) == []


@pytest.mark.asyncio
async def test_fremdes_produkt_bleibt_unsichtbar_trotz_passendem_fach(db_session):
    fach = await _fach(db_session, "AN1Physik")
    gruppe = await _gruppe(db_session, "AN1P1", fach)
    await _artefakt(db_session, FREMD, "gehört jemand anderem", fach=fach)

    assert await store.list_artifacts(db_session, ICH, group_id=gruppe) == []
    assert await store.list_artifacts(db_session, ICH, subject_id=fach) == []
    assert await store.list_artifacts(db_session, ICH) == []


@pytest.mark.asyncio
async def test_limit_kappt_die_neuesten(db_session):
    fach = await _fach(db_session, "AN1Sport")
    for i in range(4):
        await _artefakt(db_session, ICH, f"Nr {i}", fach=fach, versatz_min=i)

    treffer = await store.list_artifacts(db_session, ICH, subject_id=fach, limit=2)

    assert [a.title for a in treffer] == ["Nr 3", "Nr 2"]


# ── Herkunft beim Speichern ──────────────────────────────────────────────────

async def _nachricht(db, chat) -> Message:
    msg = Message(id=uuid4(), conversation_id=chat.id, role="assistant", content="x",
                  provider_model="mistral/mistral-small-latest")
    db.add(msg)
    await db.flush()
    return msg


@pytest.mark.asyncio
async def test_herkunft_nimmt_das_fach_der_gruppe_wenn_der_chat_keins_hat(db_session):
    """Schüler-Chats tragen oft nur die Gruppe."""
    fach = await _fach(db_session, "AN1Bio")
    gruppe = await _gruppe(db_session, "AN1Bio7", fach)
    assistent = Assistant(name="AN1 Lernhilfe", system_prompt="P", model="", audience="student",
                          scope="all_students", suggest="never", fallbacks=[])
    db_session.add(assistent)
    await db_session.flush()
    chat = await _chat(db_session, ICH, group_id=gruppe, assistant_id=assistent.id)
    msg = await _nachricht(db_session, chat)

    h = await promote.herkunft(db_session, pseudonym=ICH, message_id=msg.id)

    assert h == promote.Herkunft("mistral/mistral-small-latest", chat.id, fach, "AN1 Lernhilfe")


@pytest.mark.asyncio
async def test_fremde_konversation_liefert_keine_herkunft(db_session):
    fach = await _fach(db_session, "AN1Kunst")
    chat = await _chat(db_session, FREMD, subject_id=fach)
    msg = await _nachricht(db_session, chat)

    assert await promote.herkunft(db_session, pseudonym=ICH, message_id=msg.id) == promote.KEINE_HERKUNFT
    assert await promote.herkunft(db_session, pseudonym=ICH, conversation_id=chat.id) == promote.KEINE_HERKUNFT


@pytest.mark.asyncio
async def test_fach_ueberlebt_das_loeschen_des_chats(db_session):
    """Der Grund für die Spalte: Der Chat geht nach 93 Tagen, das Fach bleibt am Produkt.

    (`store.save_artifact` schreibt fest — in der zurückgerollten Test-Sitzung wird die Zeile
    deshalb mit den Werten der Herkunft direkt angelegt; den Speicherweg prüft
    `test_artifact_promote.py`.)
    """
    fach = await _fach(db_session, "AN1Geo")
    chat = await _chat(db_session, ICH, subject_id=fach)
    msg = await _nachricht(db_session, chat)
    h = await promote.herkunft(db_session, pseudonym=ICH, message_id=msg.id)
    doc = await _artefakt(db_session, ICH, "Blatt", fach=h.subject_id, chat=chat)

    await db_session.execute(sa.delete(Conversation).where(Conversation.id == chat.id))
    await db_session.flush()

    assert [a.id for a in await store.list_artifacts(db_session, ICH, subject_id=fach)] == [doc.id]


# ── Vorbelegung der Migration 0103 ───────────────────────────────────────────

def _migration():
    pfad = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0103_artifact_ordnung.py"
    spec = importlib.util.spec_from_file_location("migration_0103", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.mark.asyncio
async def test_vorbelegung_aus_der_lebenden_konversation(db_session):
    fach = await _fach(db_session, "AN1Musik")
    gruppe = await _gruppe(db_session, "AN1M5", fach)
    assistent = Assistant(name="AN1 Komponieren", system_prompt="P", model="", audience="all",
                          scope="all", suggest="never", fallbacks=[])
    db_session.add(assistent)
    await db_session.flush()
    eigener = await _chat(db_session, ICH, group_id=gruppe, assistant_id=assistent.id)
    fremder = await _chat(db_session, FREMD, subject_id=fach)
    mit_chat = await _artefakt(db_session, ICH, "aus dem Chat", chat=eigener)
    falscher_chat = await _artefakt(db_session, ICH, "fremder Chat", chat=fremder)
    ohne = await _artefakt(db_session, ICH, "ohne Chat")

    for sql in _migration().vorbelegung_sql():
        await db_session.execute(sa.text(sql))
    await db_session.flush()
    for art in (mit_chat, falscher_chat, ohne):
        await db_session.refresh(art)

    assert (mit_chat.subject_id, mit_chat.assistant_name) == (fach, "AN1 Komponieren")
    # Eine Konversation, die nicht der Eigentümer:in gehört, liefert nichts.
    assert (falscher_chat.subject_id, falscher_chat.assistant_name) == (None, None)
    assert ohne.subject_id is None
    assert ohne.updated_at == ohne.created_at
