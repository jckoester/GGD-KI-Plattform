"""Zuschläge von Hand gegen die echte Datenbank (0.12, Paket 2, AP1).

Die Rechnung steht in `test_budget_accrual.py`. Hier die Zusagen, die an der Datenbank
hängen: Ein Zuschlag endet mit dem Schuljahr (F2), gilt je Mitglied als Momentaufnahme
(F1), und ein gescheiterter Proxy-Aufruf hinterlässt **keine** Zeile — ein zweiter
Versuch bucht also nicht doppelt.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.budget.accrual import zuschlag_usd
from app.budget.zuschlag import buche_auf
from app.db.models import BudgetGrant, Group, GroupMembership, Subject

pytestmark = pytest.mark.asyncio

JAHR = "2026/27"
LEHRKRAFT = "zs-lehrkraft"
SCHUELER = ["zs-a", "zs-b", "zs-c"]
NACHZUEGLER = "zs-spaet"
ALLE = [LEHRKRAFT, *SCHUELER, NACHZUEGLER, "zs-proxy-weg", "zs-ohne-grenze"]


@pytest_asyncio.fixture
async def fabrik(async_engine):
    f = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    yield f
    async with f() as db:
        await db.execute(delete(BudgetGrant).where(BudgetGrant.pseudonym.in_(ALLE)))
        await db.execute(delete(GroupMembership).where(GroupMembership.pseudonym.in_(ALLE)))
        await db.execute(delete(Group).where(Group.slug == "teaching-zs-7b"))
        await db.commit()


def _proxy(grenzen: dict[str, float | None], kaputt: set[str] = frozenset()):
    """Attrappe des LiteLLM-Clients: `grenzen` je Pseudonym, `kaputt` wirft."""
    gesetzt: dict[str, float] = {}

    def fabrik():
        c = MagicMock()

        async def get_user(p):
            if p in kaputt:
                raise RuntimeError("Proxy weg")
            if p not in grenzen:
                return None
            return {"max_budget": grenzen[p]}

        async def update_user_budget(p, max_budget):
            gesetzt[p] = max_budget

        c.get_user = AsyncMock(side_effect=get_user)
        c.update_user_budget = AsyncMock(side_effect=update_user_budget)
        c.close = AsyncMock()
        return c

    return fabrik, gesetzt


async def _anzahl(db, pseudonym):
    return await db.scalar(
        select(func.count()).select_from(BudgetGrant).where(BudgetGrant.pseudonym == pseudonym)
    )


class TestSchuljahr:
    async def test_zaehlt_nur_das_laufende_schuljahr(self, fabrik):
        """F2: Ein Zuschlag endet mit dem Schuljahr — sonst wüchse er über Jahre mit."""
        async with fabrik() as db:
            db.add_all([
                BudgetGrant(pseudonym="zs-a", schuljahr="2025/26", betrag_usd=9.0,
                            grund="Vorjahr", erstellt_von="x"),
                BudgetGrant(pseudonym="zs-a", schuljahr=JAHR, betrag_usd=2.0,
                            grund="dieses Jahr", erstellt_von="x"),
                BudgetGrant(pseudonym="zs-a", schuljahr=JAHR, betrag_usd=0.5,
                            grund="noch einmal", erstellt_von="x"),
            ])
            await db.commit()
            assert await zuschlag_usd(db, "zs-a", JAHR) == pytest.approx(2.5)
            assert await zuschlag_usd(db, "zs-a", "2025/26") == pytest.approx(9.0)

    async def test_ohne_zuschlag_null(self, fabrik):
        async with fabrik() as db:
            assert await zuschlag_usd(db, "zs-niemand", JAHR) == 0.0


class TestBuchen:
    async def test_hebt_die_grenze_an_und_schreibt_das_protokoll(self, fabrik):
        proxy, gesetzt = _proxy({"zs-a": 3.0})
        async with fabrik() as db:
            erg = await buche_auf(db, pseudonyme=["zs-a"], betrag_usd=5.0, grund="Klausur",
                                  erstellt_von="admin-x", schuljahr=JAHR, client_fabrik=proxy)
            assert erg.gebucht == ["zs-a"]
            assert gesetzt["zs-a"] == pytest.approx(8.0)
            assert await zuschlag_usd(db, "zs-a", JAHR) == pytest.approx(5.0)
            zeile = (await db.execute(select(BudgetGrant).where(
                BudgetGrant.pseudonym == "zs-a"))).scalar_one()
            assert zeile.grund == "Klausur" and zeile.erstellt_von == "admin-x"

    async def test_proxy_fehler_hinterlaesst_keine_zeile(self, fabrik):
        """Erst Proxy, dann Zeile — ein zweiter Versuch darf nicht doppelt buchen."""
        proxy, _ = _proxy({"zs-a": 3.0}, kaputt={"zs-proxy-weg"})
        async with fabrik() as db:
            erg = await buche_auf(db, pseudonyme=["zs-a", "zs-proxy-weg"], betrag_usd=1.0,
                                  grund="Test", erstellt_von="x", schuljahr=JAHR,
                                  client_fabrik=proxy)
            assert erg.fehlgeschlagen == ["zs-proxy-weg"]
            assert await _anzahl(db, "zs-proxy-weg") == 0
            assert await _anzahl(db, "zs-a") == 1

    async def test_unbegrenztes_konto_wird_nicht_begrenzt(self, fabrik):
        """`max_budget = None` heißt „kein Limit" — darauf einen Betrag zu setzen hieße,
        ein unbegrenztes Konto zu begrenzen."""
        proxy, gesetzt = _proxy({"zs-ohne-grenze": None})
        async with fabrik() as db:
            erg = await buche_auf(db, pseudonyme=["zs-ohne-grenze"], betrag_usd=1.0,
                                  grund="Test", erstellt_von="x", schuljahr=JAHR,
                                  client_fabrik=proxy)
            assert erg.unbegrenzt == ["zs-ohne-grenze"]
            assert "zs-ohne-grenze" not in gesetzt
            assert await _anzahl(db, "zs-ohne-grenze") == 0

    async def test_doppelt_genannt_bekommt_einmal(self, fabrik):
        """Gruppe und Einzelperson überlappen — ohne Entdoppelung gäbe es zwei Beträge."""
        proxy, gesetzt = _proxy({"zs-a": 3.0})
        async with fabrik() as db:
            await buche_auf(db, pseudonyme=["zs-a", "zs-a"], betrag_usd=1.0, grund="Test",
                            erstellt_von="x", schuljahr=JAHR, client_fabrik=proxy)
            assert await _anzahl(db, "zs-a") == 1
            assert gesetzt["zs-a"] == pytest.approx(4.0)

    @pytest.mark.parametrize("betrag,grund", [(0.0, "ok"), (-1.0, "ok"), (1.0, "   ")])
    async def test_unsinn_wird_abgewiesen(self, fabrik, betrag, grund):
        async with fabrik() as db:
            with pytest.raises(ValueError):
                await buche_auf(db, pseudonyme=["zs-a"], betrag_usd=betrag, grund=grund,
                                erstellt_von="x", schuljahr=JAHR)


class TestGruppe:
    async def _gruppe(self, db) -> int:
        fach = (await db.execute(select(Subject).where(Subject.slug == "zs-fach"))).scalar_one_or_none()
        if fach is None:
            fach = Subject(slug="zs-fach", name="Zuschlagskunde")
            db.add(fach)
            await db.flush()
        g = Group(name="Zs 7b", slug="teaching-zs-7b", type="teaching_group",
                  subject_id=fach.id, sso_group_id=None)
        db.add(g)
        await db.flush()
        db.add(GroupMembership(group_id=g.id, pseudonym=LEHRKRAFT,
                               role_in_group="teacher", herkunft="eigen"))
        for s in SCHUELER:
            db.add(GroupMembership(group_id=g.id, pseudonym=s,
                                   role_in_group="student", herkunft="eigen"))
        await db.commit()
        return g.id

    async def test_spaeter_beigetreten_bekommt_nichts(self, fabrik):
        """F1, Momentaufnahme: Der Zuschlag hängt am Menschen, nicht an der
        Mitgliedschaft. Sonst wirkte ein Beitritt im Mai rückwirkend."""
        proxy, _ = _proxy({p: 1.0 for p in SCHUELER})
        async with fabrik() as db:
            gid = await self._gruppe(db)
            await buche_auf(db, pseudonyme=SCHUELER, betrag_usd=2.0, grund="Projektwoche",
                            erstellt_von="x", schuljahr=JAHR, quelle_gruppe_id=gid,
                            client_fabrik=proxy)
            db.add(GroupMembership(group_id=gid, pseudonym=NACHZUEGLER,
                                   role_in_group="student", herkunft="eigen"))
            await db.commit()
            assert await zuschlag_usd(db, NACHZUEGLER, JAHR) == 0.0
            assert await zuschlag_usd(db, SCHUELER[0], JAHR) == pytest.approx(2.0)

    async def test_gruppe_ist_vermerkt(self, fabrik):
        proxy, _ = _proxy({"zs-a": 1.0})
        async with fabrik() as db:
            gid = await self._gruppe(db)
            await buche_auf(db, pseudonyme=["zs-a"], betrag_usd=1.0, grund="x",
                            erstellt_von="x", schuljahr=JAHR, quelle_gruppe_id=gid,
                            client_fabrik=proxy)
            zeile = (await db.execute(select(BudgetGrant).where(
                BudgetGrant.pseudonym == "zs-a"))).scalar_one()
            assert zeile.quelle_gruppe_id == gid

    async def test_geloeschte_gruppe_laesst_das_protokoll_stehen(self, fabrik):
        """`ON DELETE SET NULL`: Die Zeile ist Protokoll und bleibt; nur der Verweis geht."""
        proxy, _ = _proxy({"zs-a": 1.0})
        async with fabrik() as db:
            gid = await self._gruppe(db)
            await buche_auf(db, pseudonyme=["zs-a"], betrag_usd=1.0, grund="x",
                            erstellt_von="x", schuljahr=JAHR, quelle_gruppe_id=gid,
                            client_fabrik=proxy)
            await db.execute(delete(GroupMembership).where(GroupMembership.group_id == gid))
            await db.execute(delete(Group).where(Group.id == gid))
            await db.commit()
            zeile = (await db.execute(select(BudgetGrant).where(
                BudgetGrant.pseudonym == "zs-a"))).scalar_one()
            assert zeile.quelle_gruppe_id is None


class TestVorschauEinerGruppe:
    """Der Probelauf über den Endpunkt, gegen eine echte Gruppe."""

    async def _vorschau(self, db, gid, mitglieder):
        from app.api.admin.budgets import ZuschlagAnfrage, zuschlag_buchen
        from app.auth.jwt import JwtPayload

        return await zuschlag_buchen(
            ZuschlagAnfrage(betrag_eur=0.5, grund="Projektwoche", gruppe_id=gid,
                            mitglieder=mitglieder, probelauf=True),
            db=db,
            current_user=JwtPayload(sub="admin-x", roles=["admin"], grade=None,
                                    jti="j", iat=1, exp=9999999999),
        )

    async def test_alle_trifft_auch_die_lehrkraft(self, fabrik):
        """⚠️ Genau die Falle, derentwegen es den Filter gibt: „Klasse 7b aufbuchen"
        träfe ohne ihn die Lehrkraft mit. Die Vorschau sagt es — getrennt gezählt."""
        async with fabrik() as db:
            gid = await TestGruppe()._gruppe(db)
            v = await self._vorschau(db, gid, "alle")
        assert (v.anzahl, v.schueler, v.lehrkraefte) == (4, 3, 1)
        assert v.summe_eur == 2.0
        assert v.gruppenname == "Zs 7b"

    async def test_nur_schueler(self, fabrik):
        async with fabrik() as db:
            gid = await TestGruppe()._gruppe(db)
            v = await self._vorschau(db, gid, "schueler")
        assert (v.anzahl, v.schueler, v.lehrkraefte) == (3, 3, 0)
        assert v.summe_eur == 1.5

    async def test_nur_lehrkraefte(self, fabrik):
        """Der Fall „Gruppe von Lehrkräften" aus F1 — etwa eine Fachschaft."""
        async with fabrik() as db:
            gid = await TestGruppe()._gruppe(db)
            v = await self._vorschau(db, gid, "lehrkraefte")
        assert (v.anzahl, v.lehrkraefte) == (1, 1)


class TestKennungUndGruppenliste:
    """Gegen die echte Datenbank: Präfixsuche und Zählung je Rolle."""

    async def test_kennung_findet_genau_ein_konto(self, fabrik):
        from app.api.admin.budgets import _person_zur_kennung
        from app.db.models import PseudonymAudit

        voll = "c0ffee" + "1" * 58
        async with fabrik() as db:
            db.add(PseudonymAudit(pseudonym=voll, role="teacher"))
            await db.commit()
            try:
                person = await _person_zur_kennung(db, "c0ff ee11 1111")
                assert person.pseudonym == voll
            finally:
                await db.execute(delete(PseudonymAudit).where(PseudonymAudit.pseudonym == voll))
                await db.commit()

    async def test_gruppenliste_zaehlt_je_rolle(self, fabrik):
        from app.api.admin.budgets import zuschlag_gruppen

        async with fabrik() as db:
            gid = await TestGruppe()._gruppe(db)
            liste = await zuschlag_gruppen(db=db, _=None)
        eintrag = next(g for g in liste if g.id == gid)
        assert (eintrag.schueler, eintrag.lehrkraefte) == (3, 1)
        assert eintrag.name == "Zs 7b"
