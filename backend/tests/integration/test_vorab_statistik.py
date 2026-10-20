"""Die Vorab-Statistik (0.16, Schritt 3c) — Zählen gegen die Datenbank, Lesen über die API.

Der Kern ist der Schlüssel: Fach, Knoten und Stufe dürfen leer sein, und nur mit
`NULLS NOT DISTINCT` zählt `ON CONFLICT` dort hoch, statt je Nachricht eine Zeile anzulegen.
Das gehört gegen Postgres geprüft, nicht gegen einen Mock.
"""
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.context.bausteine import VORAB, WERKZEUG, Angebot, Baustein, Kontext
from app.context.vorab_statistik import zaehlen
from app.db.models import ContextNode, Subject, VorabStatistik
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

#: Eine Woche, in der sonst nichts zählt — Montag 07.01.2030.
WOCHE = date(2030, 1, 7)
ZEITPUNKT = datetime(2030, 1, 9, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def ohne_commit(db_session, monkeypatch):
    """`zaehlen` committet selbst; im Test bleibt alles in der zurückgerollten Transaktion."""
    async def _flush():
        await db_session.flush()
    monkeypatch.setattr(db_session, "commit", _flush)
    return db_session


async def _knoten(db, titel, **extra) -> str:
    k = ContextNode(category="concept", content_type="begriff", title=titel, content="Text.",
                    read_scope="school", write_scope="school", status="active", **extra)
    db.add(k)
    await db.flush()
    return str(k.id)


def _kontext(sicher=(), angebot=(), subject_id=None) -> Kontext:
    return Kontext(
        text="",
        bausteine=[Baustein(k, "T", "begriff", None, VORAB) for k in sicher],
        angebot=[Angebot(k, "T", None, "distanz") for k in angebot],
        subject_id=subject_id,
    )


async def _zeilen(db, **wo):
    bedingung = [VorabStatistik.woche == WOCHE, *(getattr(VorabStatistik, k) == v if v is not None
                                                  else getattr(VorabStatistik, k).is_(None)
                                                  for k, v in wo.items())]
    return (await db.execute(sa.select(VorabStatistik).where(*bedingung))).scalars().all()


class TestZaehlen:
    async def test_zwei_nachrichten_ohne_fach_ergeben_eine_wochenzeile(self, ohne_commit):
        for _ in range(2):
            await zaehlen(ohne_commit, kontext=_kontext(), werkzeug_bausteine=[], gesucht=False,
                          modell="chat-standard", zeitpunkt=ZEITPUNKT)
        zeilen = await _zeilen(ohne_commit, node_id=None, subject_id=None)
        assert [(z.nachrichten, z.modell) for z in zeilen] == [(2, "chat-standard")]

    async def test_anderes_modell_eigene_zeile(self, ohne_commit):
        """Gegenprobe: Das Modell gehört zum Schlüssel — gezählt wird je Modell."""
        for modell in ("chat-standard", "chat-komplex"):
            await zaehlen(ohne_commit, kontext=_kontext(), werkzeug_bausteine=[], gesucht=False,
                          modell=modell, zeitpunkt=ZEITPUNKT)
        assert len(await _zeilen(ohne_commit, node_id=None, subject_id=None)) == 2

    async def test_sicher_wegen_der_gruppe_zaehlt_in_eigener_zeile(self, ohne_commit):
        """0.20 (AC, Alembic 0089): `grund` gehört zum Schlüssel — derselbe Knoten, einmal sicher
        über die Distanz, einmal wegen der Gruppe, ergibt zwei Zeilen, keine vermischte."""
        k = await _knoten(ohne_commit, "Gemisch")
        for grund in (None, "gruppe", "gruppe"):
            kontext = Kontext(text="", bausteine=[Baustein(k, "T", "begriff", None, VORAB, grund=grund)])
            await zaehlen(ohne_commit, kontext=kontext, werkzeug_bausteine=[], gesucht=False,
                          modell="chat-standard", zeitpunkt=ZEITPUNKT)
        zeilen = await _zeilen(ohne_commit, node_id=k)
        assert sorted((z.grund or "", z.vorgelegt) for z in zeilen) == [("", 1), ("gruppe", 2)]

    async def test_schluessel_ist_nulls_not_distinct(self, ohne_commit):
        wert = (await ohne_commit.execute(sa.text(
            "SELECT indnullsnotdistinct FROM pg_index "
            "WHERE indexrelid = 'uq_vorab_statistik_schluessel'::regclass"
        ))).scalar_one()
        assert wert is True

    async def test_knoten_und_wochenzeile(self, ohne_commit):
        fach = Subject(slug=f"vs-{uuid4().hex[:8]}", name="Statistikfach", fach_code="VS1")
        ohne_commit.add(fach)
        await ohne_commit.flush()
        a, b, c = [await _knoten(ohne_commit, f"Statistik {t}") for t in "ABC"]
        await zaehlen(
            ohne_commit, kontext=_kontext(sicher=[a], angebot=[b, c], subject_id=fach.id),
            werkzeug_bausteine=[Baustein(b, "B", "begriff", None, WERKZEUG)], gesucht=True,
            modell="chat-standard", zeitpunkt=ZEITPUNKT,
        )
        knoten = {(str(z.node_id), z.stufe): (z.vorgelegt, z.im_werkzeugergebnis)
                  for z in await _zeilen(ohne_commit, subject_id=fach.id) if z.node_id}
        assert knoten == {(a, "sicher"): (1, 0), (b, "angebot"): (1, 1), (c, "angebot"): (1, 0)}
        [woche] = await _zeilen(ohne_commit, subject_id=fach.id, node_id=None)
        assert (woche.nachrichten, woche.mit_sicher, woche.mit_angebot, woche.angebot_nachgeschlagen,
                woche.angebot_ohne_sicher, woche.suchen_ohne_angebot, woche.vorgelegt) == (
            1, 1, 1, 1, 0, 0, 0)

    async def test_geloeschter_knoten_faellt_heraus_die_nachricht_zaehlt(self, ohne_commit):
        """Zwischen Suche und Zählen gelöscht — der Fremdschlüssel darf nicht alles kosten."""
        await zaehlen(ohne_commit, kontext=_kontext(angebot=[str(uuid4())]), werkzeug_bausteine=[],
                      gesucht=False, modell="chat-standard", zeitpunkt=ZEITPUNKT)
        zeilen = await _zeilen(ohne_commit, subject_id=None)
        assert [(z.node_id, z.nachrichten, z.mit_angebot, z.angebot_ohne_sicher) for z in zeilen] == [
            (None, 1, 1, 1)]


# ── Lesen über die API ────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def bestand(async_engine):
    """Zwei Wochen Zähler in einem eigenen Fach und im Chat ohne Fach, dazu drei Knoten —
    einer davon privat bei jemand anderem."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        fach = Subject(slug=f"vs-{uuid4().hex[:8]}", name="Statistik-Chemie", fach_code="VS2")
        s.add(fach)
        await s.flush()
        stoff = await _knoten(s, "Statistikprobe Stoffe", subject_id=fach.id)
        ion = await _knoten(s, "Statistikprobe Ion")
        geheim = await _knoten(s, "Statistikprobe Geheim", owner_pseudonym="jemand-anderes")
        await s.execute(sa.update(ContextNode).where(ContextNode.title == "Statistikprobe Geheim")
                        .values(read_scope="private", write_scope="private"))
        kw2 = date(2030, 1, 14)
        for woche, subject_id, zeile in (
            (WOCHE, fach.id, {"nachrichten": 4, "mit_sicher": 2, "mit_angebot": 3,
                              "angebot_nachgeschlagen": 1, "angebot_ohne_sicher": 2,
                              "angebot_ohne_sicher_nachgeschlagen": 1}),
            (kw2, fach.id, {"nachrichten": 1, "suchen_ohne_angebot": 1}),
            (kw2, None, {"nachrichten": 5}),
        ):
            s.add(VorabStatistik(woche=woche, subject_id=subject_id, modell="chat-standard", **zeile))
        for woche, knoten, stufe, vorgelegt, nach in (
            (WOCHE, stoff, "angebot", 3, 1), (kw2, stoff, "angebot", 2, 0),
            (WOCHE, ion, "sicher", 2, 0), (WOCHE, geheim, "angebot", 1, 0),
        ):
            s.add(VorabStatistik(woche=woche, node_id=knoten, stufe=stufe, subject_id=fach.id,
                                 modell="chat-standard", vorgelegt=vorgelegt,
                                 im_werkzeugergebnis=nach))
        await s.commit()
    yield {"fach": fach.id, "stoff": stoff, "ion": ion, "geheim": geheim}
    async with factory() as s:
        await s.execute(sa.delete(VorabStatistik).where(VorabStatistik.woche.in_([WOCHE, kw2])))
        await s.execute(sa.delete(ContextNode).where(ContextNode.title.like("Statistikprobe %")))
        await s.execute(sa.delete(Subject).where(Subject.id == fach.id))
        await s.commit()


ZEITRAUM = "from_date=2030-01-07&to_date=2030-01-20"


class TestApi:
    async def test_lehrkraft_und_schuelerin_kommen_nicht_heran(
        self, test_client, auth_headers_teacher2, auth_headers_student,
    ):
        for kopf in (auth_headers_teacher2, auth_headers_student):
            assert (await test_client.get(f"/admin/stats/vorab?{ZEITRAUM}", headers=kopf)
                    ).status_code == 403

    async def test_rolle_statistics_darf(self, test_client, jwt_service, bestand):
        token, _ = jwt_service.issue(pseudonym=TEACHER2_PSEUDO, roles=["teacher", "statistics"],
                                     grade=None)
        antwort = await test_client.get(f"/admin/stats/vorab?{ZEITRAUM}",
                                        headers={"Cookie": f"session={token}"})
        assert antwort.status_code == 200

    async def test_wochen_summiert_ueber_faecher(self, test_client, auth_headers, bestand):
        daten = (await test_client.get(f"/admin/stats/vorab?{ZEITRAUM}", headers=auth_headers)).json()
        assert [(w["woche"], w["nachrichten"]) for w in daten["wochen"]] == [
            ("2030-01-07", 4), ("2030-01-14", 6)]
        erste = daten["wochen"][0]
        assert (erste["angebot_ohne_sicher"], erste["angebot_ohne_sicher_nachgeschlagen"]) == (2, 1)
        assert {"id": bestand["fach"], "name": "Statistik-Chemie"} in daten["faecher"]

    async def test_fachfilter_und_ohne_fach(self, test_client, auth_headers, bestand):
        mit = (await test_client.get(f"/admin/stats/vorab?{ZEITRAUM}&subject_id={bestand['fach']}",
                                     headers=auth_headers)).json()
        assert [w["nachrichten"] for w in mit["wochen"]] == [4, 1]
        ohne = (await test_client.get(f"/admin/stats/vorab?{ZEITRAUM}&ohne_fach=true",
                                      headers=auth_headers)).json()
        assert [w["nachrichten"] for w in ohne["wochen"]] == [5]
        assert ohne["knoten"] == []

    async def test_knoten_summiert_und_nach_angebot_sortiert(self, test_client, auth_headers, bestand):
        daten = (await test_client.get(f"/admin/stats/vorab?{ZEITRAUM}", headers=auth_headers)).json()
        eigene = [k for k in daten["knoten"] if k["node_id"] in bestand.values()]
        assert [(k["titel"], k["fach"], k["sicher"], k["angeboten"], k["nachgeschlagen"])
                for k in eigene] == [
            ("Statistikprobe Stoffe", "Statistik-Chemie", 0, 5, 1),
            (None, None, 0, 1, 0),
            ("Statistikprobe Ion", None, 2, 0, 0),
        ]

    async def test_zeitraum_schneidet_wochen_ab(self, test_client, auth_headers, bestand):
        """Gegenprobe zum Zeitraum: Nur die erste Woche — die zweite zählt nirgends mit."""
        daten = (await test_client.get("/admin/stats/vorab?from_date=2030-01-09&to_date=2030-01-13",
                                       headers=auth_headers)).json()
        assert [w["woche"] for w in daten["wochen"]] == ["2030-01-07"]
        stoff = next(k for k in daten["knoten"] if k["node_id"] == bestand["stoff"])
        assert stoff["angeboten"] == 3

    async def test_umgekehrter_zeitraum_wird_abgewiesen(self, test_client, auth_headers):
        antwort = await test_client.get("/admin/stats/vorab?from_date=2030-02-01&to_date=2030-01-01",
                                        headers=auth_headers)
        assert antwort.status_code == 422
