"""Das Reparaturskript für verstümmelte Herkunftsdateien (0.14, Schritt 8).

Nachgestellt wird der Stand auf Prod: Knoten, die ein Zip-Import mit falsch gelesenen
Dateinamen angelegt hat — Herkunftsdatei `Hu╠êckel-Regel`, abgeleitete Kennung
`…-hu-ckel-regel`. Inhalt und Vektor sind in Ordnung und müssen es bleiben.
"""
import uuid
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.context.fachbegriffe_import import importiere, leite_id_ab
from app.context.fachbegriffe_namen import namen_reparieren
from app.db.models import ContextNode, Subject

pytestmark = pytest.mark.asyncio

VORHER = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def bestand(async_engine, db_url):
    """Ein Fach mit Fachschaft und vier Knoten:
    `hueckel` — verstümmelt, Kennung abgeleitet;
    `sigma` — verstümmelt, Kennung aus dem Frontmatter;
    `bruecken` — verstümmelt, aber ein Zwilling trägt die richtige Kennung schon;
    `ion` — richtig."""
    kennung = uuid.uuid4().hex[:4]
    code = f"NR{kennung}"
    sync = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with sync.cursor() as cur:
        cur.execute("INSERT INTO subjects (slug, name, fach_code) VALUES (%s, 'Namensfach', %s)"
                    " RETURNING id", (f"namensfach-{kennung}", code))
        sid = cur.fetchone()[0]
        cur.execute("INSERT INTO groups (name, slug, type, subject_id, sso_group_id) VALUES"
                    " (%s, %s, 'subject_department', %s, %s) RETURNING id",
                    (f"FS Namensfach {kennung}", f"fs-namen-{kennung}", sid, f"fs-namen-{kennung}"))
        gid = cur.fetchone()[0]
    sync.commit()

    vektor = "[" + ",".join(["0.25"] * settings.embedding_dimensions) + "]"

    def knoten(cur, titel, quelle, seed_id):
        cur.execute(
            "INSERT INTO context_nodes (category, content_type, title, content, subject_id,"
            " read_scope, write_scope, write_scope_group_id, status, embedding, metadata,"
            " created_at, updated_at) VALUES ('concept', 'begriff', %s, %s, %s, 'school',"
            " 'subject', %s, 'active', %s, %s, %s, %s) RETURNING id",
            (titel, f"Ein Text über {titel}.", sid, gid, vektor,
             psycopg2.extras.Json({"seed_quelle": quelle, "seed_id": seed_id}),
             VORHER, VORHER))
        return cur.fetchone()[0]

    with sync.cursor() as cur:
        ids = {
            "hueckel": knoten(cur, "Hückel-Regel", "Hu╠êckel-Regel",
                              leite_id_ab(code, "Hu╠êckel-Regel")),
            "sigma": knoten(cur, "σ- und π-Bindung", "╧â- und ╧Ç-Bindung",
                            "nr-sigma-und-pi-bindung"),
            "bruecken": knoten(cur, "Wasserstoffbrücken", "Wasserstoffbru╠êcken",
                               leite_id_ab(code, "Wasserstoffbru╠êcken")),
            "zwilling": knoten(cur, "Wasserstoffbrücken (Zwilling)", "Wasserstoffbrücken",
                               leite_id_ab(code, "Wasserstoffbrücken")),
            "ion": knoten(cur, "Ion", "Ion", leite_id_ab(code, "Ion")),
        }
    sync.commit()
    yield {"sid": sid, "code": code, **ids}
    with sync.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = %s", (sid,))
        cur.execute("DELETE FROM groups WHERE id = %s", (gid,))
        cur.execute("DELETE FROM subjects WHERE id = %s", (sid,))
    sync.commit()
    sync.close()


@pytest.fixture
def sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _stand(sitzungen, node_id):
    async with sitzungen() as db:
        n = await db.get(ContextNode, node_id)
        return n.metadata_.get("seed_quelle"), n.metadata_.get("seed_id"), n.updated_at, n.embedding is not None


def _eigene(ergebnis, bestand):
    return [r for r in ergebnis if r.fach == "Namensfach"]


async def test_probelauf_schreibt_nichts(sitzungen, bestand):
    async with sitzungen() as db:
        ergebnis = _eigene(await namen_reparieren(db), bestand)
        await db.rollback()
    assert {r.neu_quelle for r in ergebnis} == {"Hückel-Regel", "σ- und π-Bindung", "Wasserstoffbrücken"}
    assert (await _stand(sitzungen, bestand["hueckel"]))[0] == "Hu╠êckel-Regel"


async def test_echter_lauf_repariert_und_laesst_inhalt_datum_und_vektor(sitzungen, bestand):
    async with sitzungen() as db:
        ergebnis = {r.titel: r for r in _eigene(await namen_reparieren(db), bestand)}
        await db.commit()
    code = bestand["code"].lower()

    quelle, kennung, geaendert, vektor = await _stand(sitzungen, bestand["hueckel"])
    assert (quelle, kennung) == ("Hückel-Regel", f"{code}-hueckel-regel")
    assert geaendert == VORHER, "die Reparatur ist keine inhaltliche Änderung"
    assert vektor, "der Vektor darf nicht verloren gehen"

    # Kennung aus dem Frontmatter: bleibt, nur die Herkunftsdatei wird richtig.
    assert (await _stand(sitzungen, bestand["sigma"]))[:2] == ("σ- und π-Bindung", "nr-sigma-und-pi-bindung")

    # Kollision: gemeldet, nichts geschrieben.
    assert ergebnis["Wasserstoffbrücken"].kollision == "Wasserstoffbrücken (Zwilling)"
    assert (await _stand(sitzungen, bestand["bruecken"]))[0] == "Wasserstoffbru╠êcken"

    # Richtige Namen tauchen gar nicht auf.
    assert "Ion" not in ergebnis


async def test_zweiter_lauf_findet_nur_noch_die_kollision(sitzungen, bestand):
    for _ in range(2):
        async with sitzungen() as db:
            ergebnis = _eigene(await namen_reparieren(db), bestand)
            await db.commit()
    assert [(r.titel, r.kollision is not None) for r in ergebnis] == [("Wasserstoffbrücken", True)]


async def test_neuimport_nach_der_reparatur_legt_keinen_zweiten_knoten_an(sitzungen, bestand):
    async with sitzungen() as db:
        await namen_reparieren(db)
        await db.commit()
    datei = (b"---\nknotentyp: begriff\ntitel: H\xc3\xbcckel-Regel\n---\n\n"
             b"Ein Text \xc3\xbcber H\xc3\xbcckel-Regel.\n")
    async with sitzungen() as db:
        fach = await db.get(Subject, bestand["sid"])
        bilanz = await importiere(db, {"Hückel-Regel.md": datei}, nur_fach=fach)
        await db.commit()
    assert bilanz.neu == 0, [(d.datei, d.zustand) for d in bilanz.dateien]
    async with sitzungen() as db:
        anzahl = (await db.execute(sa.select(sa.func.count()).where(
            ContextNode.subject_id == bestand["sid"], ContextNode.title == "Hückel-Regel"))).scalar()
    assert anzahl == 1
