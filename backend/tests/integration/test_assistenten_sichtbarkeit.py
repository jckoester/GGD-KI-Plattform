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
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from app.assistants.sichtbarkeit import (
    GRUENDE, Zugang, darf_nutzen, lade_zugang, sichtbar_klausel, warum_nicht,
)
from app.auth.jwt import JwtPayload
from app.db.models import Assistant, Group, GroupMembership, Subject

pytestmark = pytest.mark.asyncio

ERSTELLERIN = "lehrkraft-erstellerin"
GRUPPENLEHRKRAFT = "lehrkraft-der-gruppe"
FREMDE_LEHRKRAFT = "lehrkraft-fremd"
SCHUELERIN = "schuelerin-der-gruppe"
FREMDE_SCHUELERIN = "schuelerin-fremd"


def _jwt(pseudonym: str, *rollen: str, grade: str | None = None) -> JwtPayload:
    return JwtPayload(
        sub=pseudonym, roles=list(rollen), grade=grade,
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


async def _zugang(db_session, pseudonym: str, *rollen: str, grade: str | None = None) -> Zugang:
    return await lade_zugang(db_session, _jwt(pseudonym, *rollen, grade=grade))


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
            # Klassenstufen (0.22, C1): beide Grenzen, nur unten, nur oben, eigener, Gruppe
            await _assistent(db_session, scope="all_students", audience="student",
                             min_grade=8, max_grade=13, created_by="wer-anders"),
            await _assistent(db_session, scope="all", audience="all",
                             min_grade=5, max_grade=7, created_by="wer-anders"),
            await _assistent(db_session, scope="all", audience="student", min_grade=10,
                             created_by="wer-anders"),
            await _assistent(db_session, scope="all", audience="student", max_grade=6,
                             created_by="wer-anders"),
            await _assistent(db_session, scope="all_students", audience="student",
                             min_grade=11, max_grade=13),
            await _assistent(
                db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id,
                audience="student", min_grade=10, max_grade=13,
                created_by="irgendeine-kollegin",
            ),
            # Seit 0.32 (Gründe): weitere Status, Zeitfenster, Fachschaft, Zielgruppe in der Gruppe
            await _assistent(db_session, scope="all", audience="all", status="pending_review",
                             created_by="wer-anders"),
            await _assistent(db_session, scope="all", audience="all", status="disabled",
                             created_by="wer-anders"),
            await _assistent(db_session, scope="all", audience="all", created_by="wer-anders",
                             available_from=datetime.now(timezone.utc) + timedelta(days=3)),
            await _assistent(db_session, scope="all", audience="all", created_by="wer-anders",
                             available_until=datetime.now(timezone.utc) - timedelta(days=3)),
            await _assistent(db_session, scope="subject_department", audience="student",
                             scope_group_id=welt["fremde_gruppe"].id, created_by="wer-anders"),
            await _assistent(db_session, scope="teaching_group", audience="teacher",
                             scope_group_id=welt["gruppe"].id, created_by="wer-anders"),
        ]

    @pytest.mark.parametrize(
        "pseudonym,rollen,grade",
        [
            (SCHUELERIN, ("student",), None),
            (SCHUELERIN, ("student",), "5"),
            (SCHUELERIN, ("student",), "9"),
            (SCHUELERIN, ("student",), "12"),
            (SCHUELERIN, ("student",), "J1"),
            (FREMDE_SCHUELERIN, ("student",), "9"),
            (GRUPPENLEHRKRAFT, ("teacher",), None),
            (FREMDE_LEHRKRAFT, ("teacher",), None),
            (ERSTELLERIN, ("teacher",), None),
            ("admin-person", ("teacher", "admin"), None),
        ],
    )
    async def test_dieselbe_menge(self, db_session, welt, pseudonym, rollen, grade):
        bestand = await self._bestand(db_session, welt)
        ids = [a.id for a in bestand]
        zugang = await _zugang(db_session, pseudonym, *rollen, grade=grade)

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

        # Die dritte Darstellung (0.32): kein Grund genau dann, wenn die Funktion ja sagt —
        # und jeder Grund ist einer, den die Oberfläche kennt.
        gruende = {a.id: warum_nicht(a, zugang) for a in bestand}
        assert {i for i, g in gruende.items() if g is None} == aus_der_funktion, pseudonym
        assert set(gruende.values()) - {None} <= GRUENDE

    async def test_der_bestand_deckt_beide_antworten_ab(self, db_session, welt):
        """Ein Vergleich zweier leerer Mengen belegt nichts."""
        bestand = await self._bestand(db_session, welt)
        zugang = await _zugang(db_session, SCHUELERIN, "student")
        sichtbar = {a.id for a in bestand if darf_nutzen(a, zugang)}
        assert sichtbar and len(sichtbar) < len(bestand)


class TestKlassenstufe:
    """0.22 (Päckchen C1, F1/F2): Klassenstufen wirken — nur für Schüler:innen mit bekannter Stufe."""

    async def test_fuenftklaesslerin_sieht_kl_8_bis_13_nicht(self, db_session, welt):
        a = await _assistent(db_session, scope="all_students", min_grade=8, max_grade=13,
                             created_by="wer-anders")
        assert not darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student", grade="5"))
        assert darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student", grade="9"))

    async def test_grenzen_gehoeren_dazu(self, db_session, welt):
        a = await _assistent(db_session, scope="all_students", min_grade=8, max_grade=13,
                             created_by="wer-anders")
        for stufe, soll in (("7", False), ("8", True), ("13", True)):
            assert darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student", grade=stufe)) is soll

    async def test_stufe_unbekannt_wird_nicht_ausgeschlossen(self, db_session, welt):
        a = await _assistent(db_session, scope="all_students", min_grade=8, max_grade=13,
                             created_by="wer-anders")
        assert darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student"))
        assert darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student", grade="J1"))

    async def test_lehrkraft_sieht_alle_stufen(self, db_session, welt):
        a = await _assistent(db_session, scope="all", audience="all", min_grade=11,
                             created_by="wer-anders")
        assert darf_nutzen(a, await _zugang(db_session, FREMDE_LEHRKRAFT, "teacher", grade="5"))

    async def test_gruppe_und_stufe_gelten_beide(self, db_session, welt):
        a = await _assistent(db_session, scope="teaching_group", scope_group_id=welt["gruppe"].id,
                             min_grade=10, created_by="irgendeine-kollegin")
        assert not darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student", grade="9"))
        assert darf_nutzen(a, await _zugang(db_session, SCHUELERIN, "student", grade="10"))
        assert darf_nutzen(a, await _zugang(db_session, GRUPPENLEHRKRAFT, "teacher"))


class TestModellfreigabe:
    """0.27 (Plan Schritt 6, F5 a): Ein Assistent, dessen Modell für Rolle und Jahrgang nicht
    freigeschaltet ist, ist unsichtbar und nicht benutzbar — auch für seine Erstellerin.
    `modelle=None` (Freigaben unbekannt) filtert nicht."""

    @staticmethod
    def _mit(zugang, *modelle):
        from dataclasses import replace
        return replace(zugang, modelle=frozenset(modelle))

    async def test_gesperrtes_modell_ausgeblendet(self, db_session, welt, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "chat_default_model", "chat-standard")
        komplex = await _assistent(db_session, scope="all", audience="all", model="chat-komplex",
                                   created_by="wer-anders")
        standard = await _assistent(db_session, scope="all", audience="all", model="",
                                    created_by="wer-anders")
        eigener = await _assistent(db_session, scope="private", model="chat-komplex")
        bestand = [komplex, standard, eigener]
        ids = [a.id for a in bestand]

        for zugang, soll in (
            (self._mit(await _zugang(db_session, SCHUELERIN, "student", grade="7"), "chat-standard"),
             {standard.id}),
            (self._mit(await _zugang(db_session, ERSTELLERIN, "teacher"), "chat-standard"),
             {standard.id}),
            (self._mit(await _zugang(db_session, ERSTELLERIN, "teacher"), "chat-standard", "chat-komplex"),
             {komplex.id, standard.id, eigener.id}),
            (self._mit(await _zugang(db_session, SCHUELERIN, "student", grade="7"), "chat-komplex"),
             {komplex.id}),       # Standardmodell nicht frei → auch der Assistent ohne Modell nicht
            (await _zugang(db_session, SCHUELERIN, "student", grade="7"),   # unbekannt
             {komplex.id, standard.id}),
        ):
            aus_der_funktion = {a.id for a in bestand if darf_nutzen(a, zugang)}
            aus_der_abfrage = set((await db_session.execute(
                sa.select(Assistant.id).where(Assistant.id.in_(ids), sichtbar_klausel(zugang))
            )).scalars().all())
            assert aus_der_funktion == soll, (zugang.modelle, aus_der_funktion)
            assert aus_der_abfrage == soll, (zugang.modelle, aus_der_abfrage)


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


# ── Vorschau (0.29, ADR-016, Ansatz C) ──────────────────────────────────────────

def _vorschau_jwt(pseudonym, gruppe_id, *, grade="9", assistent_id=None) -> JwtPayload:
    """Ein Vorschau-Token: Rolle `student`, echte Rollen nur im Merkmal."""
    from app.auth.vorschau import Vorschau

    return JwtPayload(
        sub=pseudonym, roles=["student"], grade=grade,
        jti="00000000-0000-4000-8000-000000000001", iat=0, exp=2**31,
        preview=Vorschau(echte_rollen=["teacher"], gruppe_id=gruppe_id,
                         assistent_id=assistent_id, beginn=0, sitzung_ablauf=2**31),
    )


async def _vorschau_zugang(db_session, pseudonym, gruppe_id, **kw) -> Zugang:
    from app.auth import vorschau

    jwt = _vorschau_jwt(pseudonym, gruppe_id, **kw)
    vorschau.fuer_anfrage(jwt)  # wie `get_current_user` je Anfrage
    return await lade_zugang(db_session, jwt)


class TestVorschau:
    """Die Lehrkraft der Gruppe sieht in der Vorschau, was ihre Schüler:innen sehen."""

    async def test_eigener_entwurf_und_eigener_privater_sind_unsichtbar(self, db_session, welt):
        entwurf = await _assistent(db_session, scope="all", audience="student",
                                   status="draft", created_by=GRUPPENLEHRKRAFT)
        privat = await _assistent(db_session, scope="private", audience="all",
                                  created_by=GRUPPENLEHRKRAFT)
        zugang = await _vorschau_zugang(db_session, GRUPPENLEHRKRAFT, welt["gruppe"].id)
        assert not darf_nutzen(entwurf, zugang)
        assert not darf_nutzen(privat, zugang)

    async def test_gruppenassistent_fuer_schuelerinnen_ist_sichtbar(self, db_session, welt):
        a = await _assistent(db_session, scope="teaching_group",
                             scope_group_id=welt["gruppe"].id, audience="student",
                             created_by="irgendeine-kollegin")
        zugang = await _vorschau_zugang(db_session, GRUPPENLEHRKRAFT, welt["gruppe"].id)
        assert zugang.gruppen == {welt["gruppe"].id}
        assert zugang.lehrgruppen == frozenset(), "In der Vorschau keine Lehrkraft der Gruppe"
        assert darf_nutzen(a, zugang)

    async def test_lehrkraeftefreigabe_der_eigenen_gruppe_ist_unsichtbar(self, db_session, welt):
        """Als Lehrkraft der Gruppe sähe sie einen Assistenten für Lehrkräfte — als
        Schüler:in nicht."""
        a = await _assistent(db_session, scope="teaching_group",
                             scope_group_id=welt["gruppe"].id, audience="teacher",
                             created_by="irgendeine-kollegin")
        zugang = await _vorschau_zugang(db_session, GRUPPENLEHRKRAFT, welt["gruppe"].id)
        assert not darf_nutzen(a, zugang)

    async def test_ohne_gruppe_keine_gruppenassistenten(self, db_session, welt):
        a = await _assistent(db_session, scope="teaching_group",
                             scope_group_id=welt["gruppe"].id, audience="student",
                             created_by="irgendeine-kollegin")
        zugang = await _vorschau_zugang(db_session, GRUPPENLEHRKRAFT, None)
        assert zugang.gruppen == frozenset()
        assert not darf_nutzen(a, zugang)

    async def test_eintritt_aus_dem_editor_laesst_den_entwurf_zu(self, db_session, welt):
        """F6: Wer aus dem Editor eintritt, testet genau diesen Assistenten — auch als
        Entwurf. Die übrigen Regeln gelten trotzdem."""
        passt = await _assistent(db_session, scope="all", audience="student",
                                 status="draft", created_by=GRUPPENLEHRKRAFT)
        zu_alt = await _assistent(db_session, scope="all", audience="student",
                                  status="draft", min_grade=11, created_by=GRUPPENLEHRKRAFT)
        z1 = await _vorschau_zugang(db_session, GRUPPENLEHRKRAFT, welt["gruppe"].id,
                                    assistent_id=passt.id)
        assert darf_nutzen(passt, z1)
        z2 = await _vorschau_zugang(db_session, GRUPPENLEHRKRAFT, welt["gruppe"].id,
                                    assistent_id=zu_alt.id)
        assert not darf_nutzen(zu_alt, z2), "Klasse 9 sieht einen Assistenten ab Klasse 11 nicht"

    async def test_fremder_entwurf_wird_durch_den_eintritt_nicht_frei(self, db_session, welt):
        fremd = await _assistent(db_session, scope="all", audience="student",
                                 status="draft", created_by="irgendeine-kollegin")
        zugang = await _vorschau_zugang(db_session, GRUPPENLEHRKRAFT, welt["gruppe"].id,
                                        assistent_id=fremd.id)
        assert not darf_nutzen(fremd, zugang)

    @pytest.mark.parametrize("mit_gruppe,mit_eintritt", [
        (True, False), (False, False), (True, True),
    ])
    async def test_funktion_und_abfrage_sagen_dasselbe(self, db_session, welt, mit_gruppe, mit_eintritt):
        bestand = await TestFunktionUndAbfrageSagenDasselbe()._bestand(db_session, welt)
        bestand += [
            await _assistent(db_session, scope="all", audience="student", status="draft",
                             created_by=GRUPPENLEHRKRAFT),
            await _assistent(db_session, scope="private", audience="all",
                             created_by=GRUPPENLEHRKRAFT),
            await _assistent(db_session, scope="teaching_group", audience="teacher",
                             scope_group_id=welt["gruppe"].id, created_by="irgendeine-kollegin"),
        ]
        ids = [a.id for a in bestand]
        zugang = await _vorschau_zugang(
            db_session, GRUPPENLEHRKRAFT, welt["gruppe"].id if mit_gruppe else None,
            assistent_id=bestand[-3].id if mit_eintritt else None,
        )
        aus_der_funktion = {a.id for a in bestand if darf_nutzen(a, zugang)}
        aus_der_abfrage = set((await db_session.execute(
            sa.select(Assistant.id).where(Assistant.id.in_(ids), sichtbar_klausel(zugang))
        )).scalars().all())
        assert aus_der_funktion == aus_der_abfrage
        assert aus_der_funktion, "Ein Vergleich zweier leerer Mengen belegt nichts"


class TestWarumNicht:
    """Der Grund eines Neins (0.32, Päckchen AJ) — je Grund ein Fall.

    Der Zugang ist der, den der Reiter „Assistenten“ für eine Schüler:in der Gruppe nachbaut:
    Mitglied nur dieser Gruppe, ``eigene=False`` — eigene Entwürfe der Lehrkraft zählen nicht.
    """

    def _schuelerin(self, welt, *, stufe=9, modelle=None) -> Zugang:
        return Zugang(pseudonym="nachgebaut", rollen=frozenset({"student"}),
                      gruppen=frozenset({welt["gruppe"].id}), lehrgruppen=frozenset(),
                      stufe=stufe, modelle=modelle, eigene=False)

    @pytest.mark.parametrize("felder,grund", [
        ({"status": "draft"}, "entwurf"),
        ({"status": "pending_review"}, "in_pruefung"),
        ({"status": "disabled"}, "deaktiviert"),
        ({"status": "archived"}, "archiviert"),
        ({"min_grade": 10}, "stufe"),
        ({"scope": "teachers", "audience": "teacher"}, "nur_lehrkraefte"),
        ({"scope": "all", "audience": "teacher"}, "nur_lehrkraefte"),
        ({"scope": "private"}, "privat"),
        ({"scope": "teaching_group", "scope_group_id": None}, "ohne_gruppe"),
    ])
    async def test_grund(self, db_session, welt, felder, grund):
        a = await _assistent(db_session, **felder)
        assert warum_nicht(a, self._schuelerin(welt)) == grund
        assert not darf_nutzen(a, self._schuelerin(welt))

    async def test_andere_gruppe_und_fachschaft(self, db_session, welt):
        andere = await _assistent(db_session, scope="teaching_group",
                                  scope_group_id=welt["fremde_gruppe"].id)
        fachschaft = await _assistent(db_session, scope="subject_department",
                                      scope_group_id=welt["fremde_gruppe"].id)
        assert warum_nicht(andere, self._schuelerin(welt)) == "andere_gruppe"
        assert warum_nicht(fachschaft, self._schuelerin(welt)) == "fachschaft"

    async def test_zeitfenster(self, db_session, welt):
        jetzt = datetime.now(timezone.utc)
        spaeter = await _assistent(db_session, available_from=jetzt + timedelta(days=1))
        vorbei = await _assistent(db_session, available_until=jetzt - timedelta(days=1))
        assert warum_nicht(spaeter, self._schuelerin(welt)) == "noch_nicht_freigeschaltet"
        assert warum_nicht(vorbei, self._schuelerin(welt)) == "abgelaufen"

    async def test_modell_nicht_freigeschaltet(self, db_session, welt):
        a = await _assistent(db_session, model="chat-komplex")
        zugang = self._schuelerin(welt, modelle=frozenset({"chat-standard"}))
        assert warum_nicht(a, zugang) == "modell"
        assert not darf_nutzen(a, zugang)

    async def test_erster_grund_gewinnt(self, db_session, welt):
        """Ein Entwurf mit falscher Stufe und fremder Gruppe ist zuerst ein Entwurf."""
        a = await _assistent(db_session, status="draft", min_grade=11, scope="teaching_group",
                             scope_group_id=welt["fremde_gruppe"].id)
        assert warum_nicht(a, self._schuelerin(welt)) == "entwurf"

    async def test_sichtbar_heisst_kein_grund(self, db_session, welt):
        fuer_die_gruppe = await _assistent(db_session, scope="teaching_group",
                                           scope_group_id=welt["gruppe"].id)
        schulweit = await _assistent(db_session, scope="all_students", min_grade=8, max_grade=10)
        for a in (fuer_die_gruppe, schulweit):
            assert warum_nicht(a, self._schuelerin(welt)) is None

    async def test_eigener_entwurf_zaehlt_in_der_nachgebauten_sicht_nicht(self, db_session, welt):
        """Für die Erstellerin selbst wäre er benutzbar — für ihre Klasse nicht."""
        a = await _assistent(db_session, scope="private", created_by=ERSTELLERIN)
        assert warum_nicht(a, await _zugang(db_session, ERSTELLERIN, "teacher")) is None
        assert warum_nicht(a, self._schuelerin(welt)) == "privat"

