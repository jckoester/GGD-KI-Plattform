"""Der Unterrichtsbezug der Bibliothek (AP3 des Fachseiten-Plans).

`artifacts` trägt weder `subject_id` noch `group_id` — die Bibliothek ist strikt
privat, ein Gruppenbesitz wäre eine falsche Aussage. Der Bezug entsteht über den
Herkunfts-Chat. Diese Tests halten fest, was dieser Weg leistet und was nicht:

* Der Eigentümerfilter überlebt den Join. Ein fremdes Artefakt bleibt unsichtbar,
  auch wenn sein Herkunfts-Chat in der gefragten Gruppe liegt.
* Ein Artefakt ohne Herkunfts-Chat taucht in keinem Auszug auf — es ist nur über die
  volle Bibliothek erreichbar. Dafür sorgt die Bedingung auf der Chat-Spalte
  (`NULL = 42` ist kein Treffer), nicht der Join-Typ; mit `outerjoin` verhält sich
  die Abfrage gleich (gegengeprüft 09.09.2026).

Gegen echtes Postgres, nicht gegen Mocks: Geprüft wird die Form der Abfrage, und
genau die kann ein Mock nicht widerlegen.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.artifacts import store
from app.db.models import Artifact, Conversation, Group, Subject

ICH = "ap3-ich"
FREMD = "ap3-fremd"

# Feste Zeitpunkte statt `now()`: Die Reihenfolge der Ergebnisse ist Teil der Zusage.
T0 = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)


async def _fach(db, name: str) -> int:
    subject = Subject(name=name, slug=f"{name.lower()}-ap3")
    db.add(subject)
    await db.flush()
    return subject.id


async def _gruppe(db, name: str, subject_id: int) -> int:
    gruppe = Group(name=name, slug=f"{name.lower()}-ap3", type="teaching_group",
                   subject_id=subject_id)
    db.add(gruppe)
    await db.flush()
    return gruppe.id


async def _chat(db, pseudonym: str, subject_id=None, group_id=None):
    conv = Conversation(id=uuid4(), pseudonym=pseudonym, model_used="gpt-4o",
                        subject_id=subject_id, group_id=group_id)
    db.add(conv)
    await db.flush()
    return conv


async def _artefakt(db, owner: str, titel: str, *, chat=None, versatz_min=0):
    art = Artifact(
        id=uuid4(), owner_pseudonym=owner, kind="document",
        mime_type="text/markdown", byte_size=10, title=titel,
        origin_conversation_id=chat.id if chat else None,
        created_at=T0 + timedelta(minutes=versatz_min),
        expires_at=T0 + timedelta(days=365),
    )
    db.add(art)
    await db.flush()
    return art


@pytest.mark.asyncio
async def test_gruppenauszug_zeigt_nur_artefakte_aus_chats_dieser_gruppe(db_session):
    fach = await _fach(db_session, "AP3Mathe")
    gruppe_a = await _gruppe(db_session, "AP3A", fach)
    gruppe_b = await _gruppe(db_session, "AP3B", fach)

    chat_a = await _chat(db_session, ICH, subject_id=fach, group_id=gruppe_a)
    chat_b = await _chat(db_session, ICH, subject_id=fach, group_id=gruppe_b)
    await _artefakt(db_session, ICH, "aus A", chat=chat_a)
    await _artefakt(db_session, ICH, "aus B", chat=chat_b)

    treffer = await store.list_artifacts(db_session, ICH, group_id=gruppe_a)

    assert [a.title for a in treffer] == ["aus A"]


@pytest.mark.asyncio
async def test_fachauszug_nimmt_alle_gruppen_des_fachs(db_session):
    fach = await _fach(db_session, "AP3Deutsch")
    anderes_fach = await _fach(db_session, "AP3Chemie")
    gruppe_a = await _gruppe(db_session, "AP3D1", fach)
    gruppe_b = await _gruppe(db_session, "AP3D2", fach)

    await _artefakt(db_session, ICH, "älter",
                    chat=await _chat(db_session, ICH, subject_id=fach, group_id=gruppe_a),
                    versatz_min=0)
    await _artefakt(db_session, ICH, "neuer",
                    chat=await _chat(db_session, ICH, subject_id=fach, group_id=gruppe_b),
                    versatz_min=5)
    await _artefakt(db_session, ICH, "anderes Fach",
                    chat=await _chat(db_session, ICH, subject_id=anderes_fach))

    treffer = await store.list_artifacts(db_session, ICH, subject_id=fach)

    # Neueste zuerst — die Reihenfolge ist Teil der Zusage, nicht Zufall.
    assert [a.title for a in treffer] == ["neuer", "älter"]


@pytest.mark.asyncio
async def test_fremdes_artefakt_bleibt_unsichtbar_trotz_passender_gruppe(db_session):
    """Der Join verengt, er fügt nichts hinzu — der Eigentümerfilter steht davor."""
    fach = await _fach(db_session, "AP3Physik")
    gruppe = await _gruppe(db_session, "AP3P1", fach)

    fremder_chat = await _chat(db_session, FREMD, subject_id=fach, group_id=gruppe)
    await _artefakt(db_session, FREMD, "gehört jemand anderem", chat=fremder_chat)

    assert await store.list_artifacts(db_session, ICH, group_id=gruppe) == []
    assert await store.list_artifacts(db_session, ICH, subject_id=fach) == []
    # Auch ungefiltert nicht — sonst wäre der Befund oben ein Zufall des Joins.
    assert await store.list_artifacts(db_session, ICH) == []


@pytest.mark.asyncio
async def test_artefakt_ohne_herkunftschat_erscheint_nur_in_der_vollen_bibliothek(db_session):
    """Die bewusste Grenze: ein in der Werkstatt aus dem Nichts angelegtes Dokument."""
    fach = await _fach(db_session, "AP3Kunst")
    gruppe = await _gruppe(db_session, "AP3K1", fach)
    await _artefakt(db_session, ICH, "frei angelegt", chat=None)

    assert await store.list_artifacts(db_session, ICH, group_id=gruppe) == []
    assert await store.list_artifacts(db_session, ICH, subject_id=fach) == []

    voll = await store.list_artifacts(db_session, ICH)
    assert [a.title for a in voll] == ["frei angelegt"]


@pytest.mark.asyncio
async def test_limit_kappt_die_neuesten(db_session):
    fach = await _fach(db_session, "AP3Sport")
    gruppe = await _gruppe(db_session, "AP3S1", fach)
    chat = await _chat(db_session, ICH, subject_id=fach, group_id=gruppe)
    for i in range(4):
        await _artefakt(db_session, ICH, f"Nr {i}", chat=chat, versatz_min=i)

    treffer = await store.list_artifacts(db_session, ICH, group_id=gruppe, limit=2)

    assert [a.title for a in treffer] == ["Nr 3", "Nr 2"]
