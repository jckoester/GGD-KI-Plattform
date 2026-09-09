"""Frühere Unterrichtsgruppen (AP6 des Fachseiten-Plans).

Der Anker ist der **eigene Inhalt**, nicht die Mitgliedschaft — die ist mit dem
Schuljahreswechsel weg (Immediate Mirror in `sync_groups`). Diese Tests halten die
beiden Zusagen fest, die dabei zählen:

* Eine Gruppe, in der ich **noch** Mitglied bin, ist keine frühere.
* Fremder Inhalt macht eine Gruppe nicht zu meiner früheren, und fremde Personen
  sehen meine nicht.
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ContextNode, Conversation, Group, GroupMembership
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def welt(async_engine):
    """Vier Gruppen: früher, aktuell, fremd, und eine nur mit Chat."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    daten = {}
    async with factory() as s:
        res = await s.execute(text(
            "INSERT INTO subjects (name, slug) VALUES ('AP6-Fach', 'ap6-fach') RETURNING id"
        ))
        fach = res.scalar_one()
        daten["fach"] = fach

        for kuerzel in ("frueher", "aktuell", "fremd", "nur_chat"):
            res = await s.execute(text(
                "INSERT INTO groups (name, slug, type, subject_id) "
                "VALUES (:n, :sl, 'teaching_group', :f) RETURNING id"
            ), {"n": f"AP6 {kuerzel}", "sl": f"ap6-{kuerzel}", "f": fach})
            daten[kuerzel] = res.scalar_one()

        # Nur in „aktuell" bin ich noch Mitglied.
        await s.execute(insert(GroupMembership).values(
            group_id=daten["aktuell"], pseudonym=TEACHER1_PSEUDO, role_in_group="teacher"
        ))

        def stunde(group_id, owner, schuljahr=None):
            return ContextNode(
                category="artifact", content_type="unterrichtsstunde",
                title=f"AP6 Stunde {group_id}", owner_pseudonym=owner,
                read_scope="group", write_scope="group",
                read_scope_group_id=group_id, write_scope_group_id=group_id,
                subject_id=fach, schuljahr=schuljahr, status="active",
            )

        s.add(stunde(daten["frueher"], TEACHER1_PSEUDO, "2025/26"))
        s.add(stunde(daten["aktuell"], TEACHER1_PSEUDO, "2026/27"))
        # Fremder Inhalt in einer Gruppe, in der ich nicht bin.
        s.add(stunde(daten["fremd"], TEACHER2_PSEUDO, "2025/26"))
        # Gruppe ohne Bausteine, aber mit eigenem Chat.
        s.add(Conversation(pseudonym=TEACHER1_PSEUDO, model_used="gpt-4o",
                           group_id=daten["nur_chat"], subject_id=fach))
        await s.commit()

    yield daten

    async with factory() as s:
        gids = [daten[k] for k in ("frueher", "aktuell", "fremd", "nur_chat")]
        await s.execute(delete(Conversation).where(Conversation.group_id.in_(gids)))
        await s.execute(delete(ContextNode).where(
            ContextNode.write_scope_group_id.in_(gids)))
        await s.execute(delete(GroupMembership).where(
            GroupMembership.group_id.in_(gids)))
        await s.execute(delete(Group).where(Group.id.in_(gids)))
        await s.execute(text("DELETE FROM subjects WHERE slug = 'ap6-fach'"))
        await s.commit()


async def _archiv(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    resp = await client.get(f"/archive/groups{'?' + query if query else ''}", headers=headers)
    assert resp.status_code == 200, resp.text
    return {g["name"]: g for g in resp.json()["items"]}


async def test_frueherer_gruppe_wird_gelistet(test_client, auth_headers, welt):
    treffer = await _archiv(test_client, auth_headers)
    assert "AP6 frueher" in treffer
    assert treffer["AP6 frueher"]["bausteine"] == 1
    assert treffer["AP6 frueher"]["schuljahr"] == "2025/26"


async def test_aktuelle_gruppe_ist_keine_fruehere(test_client, auth_headers, welt):
    """Die Mitgliedschaft entscheidet — sonst stünde jede Gruppe doppelt."""
    treffer = await _archiv(test_client, auth_headers)
    assert "AP6 aktuell" not in treffer


async def test_fremder_inhalt_macht_keine_eigene_gruppe(test_client, auth_headers, welt):
    treffer = await _archiv(test_client, auth_headers)
    assert "AP6 fremd" not in treffer


async def test_fremde_person_sieht_meine_fruehere_gruppe_nicht(
    test_client, auth_headers_teacher2, welt
):
    treffer = await _archiv(test_client, auth_headers_teacher2)
    assert "AP6 frueher" not in treffer
    assert "AP6 nur_chat" not in treffer
    # Ihre eigene sieht sie sehr wohl.
    assert "AP6 fremd" in treffer


async def test_gruppe_nur_mit_chat_erscheint_ebenfalls(test_client, auth_headers, welt):
    """Eine Gruppe kann nur Chats haben; ein Join über die Bausteine verlöre sie."""
    treffer = await _archiv(test_client, auth_headers)
    assert treffer["AP6 nur_chat"]["chats"] == 1
    assert treffer["AP6 nur_chat"]["bausteine"] == 0
    # Ohne Jahresplan gibt es kein Schuljahr — geraten wird nicht.
    assert treffer["AP6 nur_chat"]["schuljahr"] is None


async def test_fachfilter_verengt(test_client, auth_headers, welt):
    treffer = await _archiv(test_client, auth_headers, subject_id=welt["fach"])
    assert "AP6 frueher" in treffer
    leer = await _archiv(test_client, auth_headers, subject_id=999999)
    assert leer == {}


async def test_schueler_ohne_eigenen_inhalt_bekommt_leeres_archiv(
    test_client, auth_headers_student, welt
):
    treffer = await _archiv(test_client, auth_headers_student)
    assert treffer == {}


async def test_eigene_bausteine_der_frueheren_gruppe_bleiben_lesbar(
    test_client, auth_headers, welt
):
    """Die tragende Annahme des Archivs.

    Der Knoten hat `read_scope: group`, die Mitgliedschaft ist weg — sichtbar ist er
    trotzdem, weil `read_scope_clause` das Eigentum **vor** dem Scope prüft. Ohne
    diese Reihenfolge wäre das Archiv eine Liste von Namen ohne Inhalt.
    """
    resp = await test_client.get(
        f"/context/nodes?group_id={welt['frueher']}&owner=me", headers=auth_headers
    )
    assert resp.status_code == 200
    titel = [n["title"] for n in resp.json()]
    assert f"AP6 Stunde {welt['frueher']}" in titel


async def test_fremder_baustein_der_frueheren_gruppe_bleibt_verborgen(
    test_client, auth_headers_teacher2, welt
):
    """Gegenprobe: Das Archiv gibt kein Fenster auf fremdes Gruppenmaterial.

    Geprüft wird mit **teacher2** — einer einfachen Lehrkraft. `auth_headers` trägt
    zusätzlich `admin`, und für Admins hebt `read_scope_clause` die Gruppenprüfung
    bewusst auf (`app/context/visibility.py`). Mit diesem Token liefe der Test ins
    Leere und behauptete eine Zusage, die er nicht prüft.
    """
    resp = await test_client.get(
        f"/context/nodes?group_id={welt['frueher']}", headers=auth_headers_teacher2
    )
    assert resp.status_code == 200
    assert resp.json() == []
