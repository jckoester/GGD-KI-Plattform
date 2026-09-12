"""Zugangstoken (PAT) über HTTP — der zweite Auth-Weg neben dem Session-Cookie.

Der Gegenstand ist nicht die Tabelle, sondern die **Zusage**: Ein Token kommt an die
Planung und den Kontextspeicher und sonst nirgendwohin, es trägt die Rollen seiner
Besitzerin *in dem Moment*, nicht die vom Tag der Erzeugung, und es endet, wenn man es
widerruft oder wenn seine Zeit um ist.

Geprüft wird durchgehend über echte Anfragen: Der Bearer-Zweig sitzt in
`get_current_user`, an dem 156 Guard-Stellen hängen — ein Test gegen die Dienstfunktion
allein ließe offen, ob der Weg dorthin überhaupt stimmt.
"""

from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
import sqlalchemy as sa

from app.auth import tokens
from app.db.models import PersonalAccessToken, PseudonymAudit
from tests.integration.test_planning_api import TEACHER1_PSEUDO

GRUPPE = 720
FACH = 720


@pytest.fixture(scope="module")
def token_gruppe(db_url, run_migrations):
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (id, slug, name, sort_order) "
            "VALUES (%s, 'tokenkunde', 'Tokenkunde', 0) ON CONFLICT (id) DO NOTHING",
            (FACH,),
        )
        cur.execute(
            "INSERT INTO groups (id, name, slug, type, subject_id) "
            "VALUES (%s, '9t Token', 'token-9t', 'teaching_group', %s) "
            "ON CONFLICT (id) DO NOTHING",
            (GRUPPE, FACH),
        )
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group) "
            "VALUES (%s, %s, 'teacher') ON CONFLICT DO NOTHING",
            (GRUPPE, TEACHER1_PSEUDO),
        )
    conn.commit()
    conn.close()
    return sync_url


@pytest.fixture
async def db(async_engine):
    """Session **ohne** umschließende Transaktion.

    `db_session` aus dem conftest rollt am Ende zurück; die Dienstfunktionen hier
    committen aber selbst, und ein `commit()` in einer fremden Transaktion bricht sie ab
    („Can't operate on closed transaction"). Aufgeräumt wird deshalb von Hand.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sitzung:
        yield sitzung


@pytest.fixture
async def audit(db):
    """Der Rollensatz, aus dem ein Token bei jeder Anfrage seine Rollen zieht.

    Wird nach jedem Test **zurückgesetzt**: `pseudonym_audit` ist geteilter Zustand, und
    zwei Tests hier entziehen absichtlich Rollen. Bliebe das stehen, fielen andere
    Integrationstests derselben Lehrkraft darüber — ein Fehlschlag weit weg von seiner
    Ursache.
    """
    vorher = await db.get(PseudonymAudit, TEACHER1_PSEUDO)
    gab_es = vorher is not None
    alt = (
        {"role": vorher.role, "roles": vorher.roles, "grade": vorher.grade,
         "revoked_all_before": vorher.revoked_all_before}
        if gab_es else None
    )

    if not gab_es:
        vorher = PseudonymAudit(pseudonym=TEACHER1_PSEUDO, role="teacher",
                                roles=["teacher", "admin"], grade=None)
        db.add(vorher)
    else:
        vorher.role = "teacher"
        vorher.roles = ["teacher", "admin"]
        vorher.revoked_all_before = None
    await db.commit()

    yield vorher

    zeile = await db.get(PseudonymAudit, TEACHER1_PSEUDO)
    if zeile is not None:
        if gab_es:
            for feld, wert in alt.items():
                setattr(zeile, feld, wert)
        else:
            await db.delete(zeile)
    await db.execute(
        sa.delete(PersonalAccessToken).where(
            PersonalAccessToken.pseudonym == TEACHER1_PSEUDO
        )
    )
    await db.commit()


@pytest.fixture
async def voller_zugang(db, audit):
    """Ein Token mit allen vier Scopes."""
    klartext, zeile = await tokens.erzeuge(
        db,
        pseudonym=TEACHER1_PSEUDO,
        name="Testgerät",
        scopes=sorted(tokens.SCOPES),
        gueltig_bis=datetime.now(timezone.utc) + timedelta(days=30),
        rollen=["teacher"],
    )
    return {"Authorization": f"Bearer {klartext}"}, zeile, klartext


class TestDerZweiteAuthWeg:
    async def test_token_kommt_an_die_planung(
        self, test_client, voller_zugang, token_gruppe
    ):
        kopf, _, _ = voller_zugang
        resp = await test_client.get(f"/planning/groups/{GRUPPE}/overview", headers=kopf)
        assert resp.status_code == 200, resp.text

    async def test_token_kommt_an_den_kontextspeicher(self, test_client, voller_zugang):
        kopf, _, _ = voller_zugang
        resp = await test_client.get("/context/nodes?limit=1", headers=kopf)
        assert resp.status_code == 200, resp.text

    async def test_ohne_kopfzeile_bleibt_es_bei_401(self, test_client):
        resp = await test_client.get("/context/nodes?limit=1")
        assert resp.status_code == 401

    async def test_erfundenes_token_ist_401(self, test_client):
        resp = await test_client.get(
            "/context/nodes?limit=1",
            # ASCII, wie ein echtes Token: HTTP-Kopfzeilen tragen nichts anderes.
            headers={"Authorization": f"Bearer {tokens.PRAEFIX}voellig-ausgedacht"},
        )
        assert resp.status_code == 401

    async def test_cookie_hat_vorrang_und_bleibt_volle_sitzung(
        self, test_client, auth_headers, voller_zugang
    ):
        """Beides gleichzeitig: Die Sitzung gewinnt, das Gatter greift nicht.

        Sonst verlöre ein eingeloggter Mensch mit gesetztem Header plötzlich den Zugang
        zu allem außerhalb der Tabelle.
        """
        kopf, _, _ = voller_zugang
        resp = await test_client.get("/budget/me", headers={**auth_headers, **kopf})
        assert resp.status_code != 403, resp.text


class TestGesperrteBereiche:
    """Die eigentliche Sicherheitszusage: Ein Token erreicht nur, was die Tabelle nennt."""

    @pytest.mark.parametrize("pfad", ["/budget/me", "/assistants", "/groups/me"])
    async def test_fremde_router_sind_403(self, test_client, voller_zugang, pfad):
        kopf, _, _ = voller_zugang
        resp = await test_client.get(pfad, headers=kopf)
        assert resp.status_code == 403, f"{pfad} antwortete {resp.status_code}"

    async def test_leserecht_erlaubt_kein_schreiben(self, test_client, db, audit):
        klartext, _ = await tokens.erzeuge(
            db, pseudonym=TEACHER1_PSEUDO, name="nur lesen",
            scopes=["context:read"],
            gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
            rollen=["teacher"],
        )
        kopf = {"Authorization": f"Bearer {klartext}"}
        assert (await test_client.get("/context/nodes?limit=1", headers=kopf)).status_code == 200
        resp = await test_client.post(
            "/context/nodes",
            json={"category": "knowledge", "content_type": "methode", "title": "X",
                  "read_scope": "school", "write_scope": "school"},
            headers=kopf,
        )
        assert resp.status_code == 403, resp.text


class TestLebenszyklus:
    async def test_widerruf_wirkt_sofort(
        self, test_client, db, voller_zugang
    ):
        kopf, zeile, _ = voller_zugang
        assert (await test_client.get("/context/nodes?limit=1", headers=kopf)).status_code == 200
        assert await tokens.widerrufe(db, zeile.id, TEACHER1_PSEUDO)
        assert (await test_client.get("/context/nodes?limit=1", headers=kopf)).status_code == 401

    async def test_fremder_kann_nicht_widerrufen(self, db, voller_zugang):
        _, zeile, _ = voller_zugang
        assert not await tokens.widerrufe(db, zeile.id, "jemand-anderes")

    async def test_abgelaufenes_token_ist_401(self, test_client, db, voller_zugang):
        kopf, zeile, _ = voller_zugang
        await db.execute(
            sa.update(PersonalAccessToken)
            .where(PersonalAccessToken.id == zeile.id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await db.commit()
        assert (await test_client.get("/context/nodes?limit=1", headers=kopf)).status_code == 401

    async def test_nutzung_wird_vermerkt(self, test_client, db, voller_zugang):
        kopf, zeile, _ = voller_zugang
        assert zeile.last_used_at is None
        await test_client.get("/context/nodes?limit=1", headers=kopf)
        frisch = (await db.execute(
            sa.select(PersonalAccessToken.last_used_at)
            .where(PersonalAccessToken.id == zeile.id)
        )).scalar()
        assert frisch is not None


class TestRollenSindFrisch:
    """Der Grund, warum keine Rollen im Token stehen."""

    async def test_entzogene_lehrkraftrolle_beendet_den_zugang(
        self, test_client, db, voller_zugang, audit
    ):
        kopf, _, _ = voller_zugang
        assert (await test_client.get("/context/nodes?limit=1", headers=kopf)).status_code == 200

        audit.roles = ["student"]
        audit.role = "student"
        await db.commit()

        resp = await test_client.get("/context/nodes?limit=1", headers=kopf)
        assert resp.status_code == 401, "Token überlebte den Rollenentzug"

    async def test_massenwiderruf_gilt_auch_fuer_token(
        self, test_client, db, voller_zugang, audit
    ):
        kopf, _, _ = voller_zugang
        assert (await test_client.get("/context/nodes?limit=1", headers=kopf)).status_code == 200

        audit.revoked_all_before = datetime.now(timezone.utc) + timedelta(seconds=1)
        await db.commit()

        resp = await test_client.get("/context/nodes?limit=1", headers=kopf)
        assert resp.status_code == 401, "Massenwiderruf ließ das Token stehen"


class TestErzeugungWehrtAb:
    async def test_schueler_bekommen_kein_token(self, db):
        with pytest.raises(tokens.TokenFehler, match="Lehrkräften"):
            await tokens.erzeuge(
                db, pseudonym="ein-kind", name="Tablet", scopes=["context:read"],
                gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
                rollen=["student"],
            )

    async def test_laenger_als_ein_jahr_geht_nicht(self, db):
        with pytest.raises(tokens.TokenFehler, match="ein Jahr"):
            await tokens.erzeuge(
                db, pseudonym=TEACHER1_PSEUDO, name="ewig",
                scopes=["context:read"],
                gueltig_bis=datetime.now(timezone.utc) + timedelta(days=400),
                rollen=["teacher"],
            )

    async def test_unbekannter_scope_wird_abgelehnt(self, db):
        with pytest.raises(tokens.TokenFehler, match="Unbekannte Berechtigung"):
            await tokens.erzeuge(
                db, pseudonym=TEACHER1_PSEUDO, name="zu viel",
                scopes=["chat:write"],
                gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
                rollen=["teacher"],
            )

    async def test_ohne_scope_ergibt_kein_token(self, db):
        with pytest.raises(tokens.TokenFehler, match="mindestens eine"):
            await tokens.erzeuge(
                db, pseudonym=TEACHER1_PSEUDO, name="leer", scopes=[],
                gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
                rollen=["teacher"],
            )


class TestDerKlartextLebtEinmal:
    async def test_in_der_datenbank_steht_nur_der_hash(self, db, voller_zugang):
        _, zeile, klartext = voller_zugang
        gespeichert = (await db.execute(
            sa.select(PersonalAccessToken.token_hash)
            .where(PersonalAccessToken.id == zeile.id)
        )).scalar()
        assert klartext not in gespeichert
        assert gespeichert != klartext
        assert len(gespeichert) == 64  # SHA-256 als Hex

    async def test_zwei_token_sind_verschieden(self, db, audit):
        a, _ = await tokens.erzeuge(
            db, pseudonym=TEACHER1_PSEUDO, name="a", scopes=["context:read"],
            gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1), rollen=["teacher"])
        b, _ = await tokens.erzeuge(
            db, pseudonym=TEACHER1_PSEUDO, name="b", scopes=["context:read"],
            gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1), rollen=["teacher"])
        assert a != b
