"""Wer darf welchen Assistenten? — gegen eine echte Datenbank.

⚠️ **Der Befund, der das ausgelöst hat** (Jan, 26.09.2026, in der Oberfläche
nachgestellt): Eine Freigabe „für diese Unterrichtsgruppe" war keine Einschränkung.
`list_assistants` filterte nie nach `scope_group_id`, und der Chat-Weg fragte eine
Funktion, die Scopes gar nicht kannte — ein **privater** Assistent war damit für jeden
benutzbar, der seine ID kannte.

Zwei Dinge werden hier geprüft, und das zweite ist das wichtigere:

1. **Die Fälle**, die der Befund nennt: Gruppenmitglied ja · fremde Schüler:in nein ·
   Ersteller:in ja · fremde Lehrkraft nein · Lehrkraft der Gruppe ja.
2. **Dass Funktion und SQL-Bedingung dasselbe sagen.** Genau das Auseinanderlaufen war
   der Fehler; es wieder möglich zu machen, indem man die Regel zweimal schreibt und
   nur einmal prüft, wäre derselbe Fehler noch einmal.
"""
import uuid

import pytest
import sqlalchemy as sa

from app.assistants.sichtbarkeit import Zugang, darf_nutzen, lade_zugang, sichtbar_klausel
from app.auth.jwt import JwtPayload
from app.db.models import Assistant, Group, GroupMembership, Subject

pytestmark = pytest.mark.asyncio

ERSTELLERIN = "lehrkraft-erstellerin"
GRUPPENLEHRKRAFT = "lehrkraft-der-gruppe"
FREMDE_LEHRKRAFT = "lehrkraft-fremd"
SCHUELERIN = "schuelerin-der-gruppe"
FREMDE_SCHUELERIN = "schuelerin-fremd"


def _jwt(pseudonym: str, *rollen: str) -> JwtPayload:
    return JwtPayload(
        sub=pseudonym, roles=list(rollen), grade=None,
        jti="00000000-0000-4000-8000-000000000000", iat=0, exp=2**31,
    )


@pytest.fixture
async def welt(db_session):
    """Eine Unterrichtsgruppe mit Lehrkraft und Schülerin, dazu zwei Fremde."""
    kennung = uuid.uuid4().hex[:8]
    fach = Subject(slug=f"sichtfach-{kennung}", name="Sichtfach")
    db_session.add(fach)
    await db_session.flush()
    gruppe = Group(
        name="Klasse 9a Sichtfach", slug=f"ug-{kennung}", type="teaching_group",
        subject_id=fach.id, sso_group_id=f"ug-{kennung}",
    )
    fremde_gruppe = Group(
        name="Klasse 9b Sichtfach", slug=f"ug2-{kennung}", type="teaching_group",
        subject_id=fach.id, sso_group_id=f"ug2-{kennung}",
    )
    db_session.add_all([gruppe, fremde_gruppe])
    await db_session.flush()
    for pseudonym, rolle in (
        (GRUPPENLEHRKRAFT, "teacher"), (SCHUELERIN, "student"),
    ):
        db_session.add(GroupMembership(
            group_id=gruppe.id, pseudonym=pseudonym, role_in_group=rolle,
            herkunft="sso",
        ))
    db_session.add(GroupMembership(
        group_id=fremde_gruppe.id, pseudonym=FREMDE_SCHUELERIN,
        role_in_group="student", herkunft="sso",
    ))
    await db_session.flush()
    return {"fach": fach, "gruppe": gruppe, "fremde_gruppe": fremde_gruppe}


async def _assistent(db_session, **felder) -> Assistant:
    vorgabe = dict(
        name=f"A-{uuid.uuid4().hex[:6]}", system_prompt="Du hilfst.", status="active",
        audience="student", scope="all", created_by=ERSTELLERIN, model="chat-standard",
    )
    assistant = Assistant(**{**vorgabe, **felder})
    db_session.add(assistant)
    await db_session.flush()
    return assistant


async def _zugang(db_session, pseudonym: str, *rollen: str) -> Zugang:
    return await lade_zugang(db_session, _jwt(pseudonym, *rollen))


class TestGruppenfreigabe:
    """Der gemeldete Fall und seine Umkehrung."""

    async def test_fremde_schuelerin_sieht_ihn_nicht(self, db_session, welt):
        """⚠️ **Der schwerere der beiden Fehler, und er war bestätigt.** Ohne diese
        Prüfung ist „für diese Unterrichtsgruppe" nur eine Beschriftung."""
        a = await _assistent(
            db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id
        )
        assert not darf_nutzen(
            a, await _zugang(db_session, FREMDE_SCHUELERIN, "student")
        )

    async def test_gruppenmitglied_sieht_ihn(self, db_session, welt):
        a = await _assistent(
            db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id
        )
        assert darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student"))

    async def test_erstellerin_sieht_ihren_eigenen(self, db_session, welt):
        """Der gemeldete Fall: Zielgruppe „Schüler:innen" schloss die Lehrkraft aus,
        die ihn angelegt hat — auch aus ihrer eigenen Liste."""
        a = await _assistent(
            db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id,
            created_by=ERSTELLERIN,
        )
        assert darf_nutzen(a, await _zugang(db_session, ERSTELLERIN, "teacher"))

    async def test_lehrkraft_der_gruppe_sieht_ihn(self, db_session, welt):
        """Entscheidung Jan, 27.09.2026: Eine Lehrkraft muss wissen, womit ihre Klasse
        arbeitet — auch wenn eine Kollegin den Assistenten angelegt hat."""
        a = await _assistent(
            db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id,
            created_by="irgendeine-kollegin",
        )
        assert darf_nutzen(a, await _zugang(db_session, GRUPPENLEHRKRAFT, "teacher"))

    async def test_fremde_lehrkraft_sieht_ihn_nicht(self, db_session, welt):
        a = await _assistent(
            db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id,
            created_by="irgendeine-kollegin",
        )
        assert not darf_nutzen(
            a, await _zugang(db_session, FREMDE_LEHRKRAFT, "teacher")
        )

    async def test_gruppenscope_ohne_gruppe_schliesst_niemanden_ein(
        self, db_session, welt
    ):
        """Das Anlegen verhindert es (422). Ein Altbestand von davor soll nicht
        versehentlich schulweit gelten — `NULL` ist keine Freigabe."""
        a = await _assistent(db_session, scope="teaching_group", scope_group_id=None)
        assert not darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student"))
        assert not darf_nutzen(
            a, await _zugang(db_session, FREMDE_SCHUELERIN, "student")
        )


class TestPrivat:
    async def test_nur_die_erstellerin(self, db_session, welt):
        """⚠️ Über den Chat-Weg war ein privater Assistent bis 09/2026 für jeden
        benutzbar, der seine ID kannte — die Listenabfrage filterte ihn, die Funktion
        nicht."""
        a = await _assistent(db_session, scope="private", audience="all")
        assert darf_nutzen(a, await _zugang(db_session, ERSTELLERIN, "teacher"))
        assert not darf_nutzen(
            a, await _zugang(db_session, FREMDE_LEHRKRAFT, "teacher")
        )
        assert not darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student"))


class TestFunktionUndAbfrageSagenDasselbe:
    """⚠️ **Der eigentliche Wächter.**

    Die Regel steht zweimal da — als Funktion für den Einzelfall und als
    SQL-Bedingung für die Liste. Genau dieses Auseinanderlaufen war der Fehler. Hier
    laufen beide über **denselben** Bestand und müssen dieselbe Menge liefern; eine
    Regel, die nur an einer Stelle gepflegt wird, fällt damit sofort auf.
    """

    async def _bestand(self, db_session, welt) -> list[Assistant]:
        return [
            await _assistent(db_session, scope="all", audience="all"),
            await _assistent(db_session, scope="all", audience="student"),
            await _assistent(db_session, scope="all", audience="teacher"),
            await _assistent(db_session, scope="all_students", audience="student"),
            await _assistent(db_session, scope="teachers", audience="teacher"),
            await _assistent(db_session, scope="private", audience="all"),
            await _assistent(
                db_session, scope="private", audience="all", created_by="wer-anders"
            ),
            await _assistent(
                db_session, scope="teaching_group",
                scope_group_id=welt["gruppe"].id, audience="student",
            ),
            await _assistent(
                db_session, scope="teaching_group",
                scope_group_id=welt["gruppe"].id, audience="student",
                created_by="irgendeine-kollegin",
            ),
            await _assistent(
                db_session, scope="teaching_group",
                scope_group_id=welt["fremde_gruppe"].id, audience="student",
                created_by="irgendeine-kollegin",
            ),
            await _assistent(db_session, scope="teaching_group", scope_group_id=None),
            await _assistent(db_session, scope="all", audience="all", status="draft"),
        ]

    @pytest.mark.parametrize(
        "pseudonym,rollen",
        [
            (SCHUELERIN, ("student",)),
            (FREMDE_SCHUELERIN, ("student",)),
            (GRUPPENLEHRKRAFT, ("teacher",)),
            (FREMDE_LEHRKRAFT, ("teacher",)),
            (ERSTELLERIN, ("teacher",)),
            ("admin-person", ("teacher", "admin")),
        ],
    )
    async def test_dieselbe_menge(self, db_session, welt, pseudonym, rollen):
        bestand = await self._bestand(db_session, welt)
        ids = [a.id for a in bestand]
        zugang = await _zugang(db_session, pseudonym, *rollen)

        aus_der_funktion = {a.id for a in bestand if darf_nutzen(a, zugang)}
        aus_der_abfrage = set((await db_session.execute(
            sa.select(Assistant.id).where(
                Assistant.id.in_(ids), sichtbar_klausel(zugang)
            )
        )).scalars().all())

        assert aus_der_funktion == aus_der_abfrage, (
            f"{pseudonym}: Funktion und Abfrage sind sich uneinig — "
            f"nur Funktion {sorted(aus_der_funktion - aus_der_abfrage)}, "
            f"nur Abfrage {sorted(aus_der_abfrage - aus_der_funktion)}"
        )

    async def test_der_bestand_deckt_beide_antworten_ab(self, db_session, welt):
        """Ein Vergleich zweier leerer Mengen belegt nichts."""
        bestand = await self._bestand(db_session, welt)
        zugang = await _zugang(db_session, SCHUELERIN, "student")
        sichtbar = {a.id for a in bestand if darf_nutzen(a, zugang)}
        assert sichtbar and len(sichtbar) < len(bestand)


class TestChatWeg:
    """Das Gegenstück am Chat — nicht nur an der Liste.

    ⚠️ Wer nur die Liste repariert, lässt einen Assistenten **über seine ID** weiter
    benutzbar. Geprüft wird die Stelle, die der Endpunkt benutzt; den Endpunkt selbst
    prüft dieses Projekt nicht über HTTP (er streamt gegen LiteLLM), sondern über seine
    Bausteine — so wie `test_crisis_chat_flow.py`.
    """

    async def test_fremde_schuelerin_bekommt_403(self, db_session, welt):
        from fastapi import HTTPException

        from app.chat.router import assistent_fuer_chat

        a = await _assistent(
            db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id
        )
        with pytest.raises(HTTPException) as fehler:
            await assistent_fuer_chat(
                db_session, a.id, _jwt(FREMDE_SCHUELERIN, "student"), testlauf=False
            )
        assert fehler.value.status_code == 403

    async def test_privater_assistent_ueber_die_id(self, db_session, welt):
        from fastapi import HTTPException

        from app.chat.router import assistent_fuer_chat

        a = await _assistent(db_session, scope="private", audience="all")
        with pytest.raises(HTTPException) as fehler:
            await assistent_fuer_chat(
                db_session, a.id, _jwt(FREMDE_LEHRKRAFT, "teacher"), testlauf=False
            )
        assert fehler.value.status_code == 403

    async def test_gruppenmitglied_kommt_durch(self, db_session, welt):
        from app.chat.router import assistent_fuer_chat

        a = await _assistent(
            db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id
        )
        geladen = await assistent_fuer_chat(
            db_session, a.id, _jwt(SCHUELERIN, "student"), testlauf=False
        )
        assert geladen.id == a.id

    async def test_testlauf_bleibt_der_lehrkraft_vorbehalten(self, db_session, welt):
        from fastapi import HTTPException

        from app.chat.router import assistent_fuer_chat

        a = await _assistent(db_session, status="draft", created_by=ERSTELLERIN)
        with pytest.raises(HTTPException) as fehler:
            await assistent_fuer_chat(
                db_session, a.id, _jwt(SCHUELERIN, "student"), testlauf=True
            )
        assert fehler.value.status_code == 403
        geladen = await assistent_fuer_chat(
            db_session, a.id, _jwt(ERSTELLERIN, "teacher"), testlauf=True
        )
        assert geladen.id == a.id

    async def test_unbekannte_id(self, db_session):
        from fastapi import HTTPException

        from app.chat.router import assistent_fuer_chat

        with pytest.raises(HTTPException) as fehler:
            await assistent_fuer_chat(
                db_session, 999_999, _jwt(SCHUELERIN, "student"), testlauf=False
            )
        assert fehler.value.status_code == 404
