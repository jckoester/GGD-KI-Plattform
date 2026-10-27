"""Päckchen AE, Schritt 2 (27.10.2026): Die Aufzählung liefert die Bildungsplan-Fassung, die
für die Stufe gilt — Kriterium K1 des Plans `Operatoren-nach-Fassung-AE-Plan.md`.

Vorher: `list_context_nodes` „erklären“ ohne Fach lieferte jede Fassung jedes Fachs (auf Dev
37 Treffer), weil Operatoren keine Kompetenznummer tragen und deshalb auch nicht
zusammenfallen. Jetzt: je Fach die Fassung der Stufe; ohne Stufe wie bisher alles.

Fahrplan wie `config/subjects.yaml` (V2 in Kraft, V3 ab 2026/27 in Kl. 5–7, wächst nach oben),
Schuljahr fest 2026/27. Biologie hat V2 und V3, Chemie nur V2 (Inhalts-Fallback).
Erfordert TEST_DATABASE_URL.
"""
import json
import uuid
from unittest.mock import patch

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.context.filters import Knotenfilter
from app.context.lookup import normalisiere_titel
from app.context.search import Suchprofil, aufzaehlung

pytestmark = pytest.mark.asyncio

FAHRPLAN = {"bildungsplan_default": {"bp_basis": "BP2016BW", "suffix": "", "editionen": [
    {"suffix": ""},
    {"suffix": ".V2", "ab_schuljahr": "2016/17", "einstieg_stufen": [5, 12]},
    {"suffix": ".V3", "ab_schuljahr": "2026/27", "einstieg_stufen": [5, 7], "wachstum": "nach_oben"},
]}}
BIO = {"id": 310, "slug": "ae-bio", "name": "AE Biologie"}
CHEM = {"id": 311, "slug": "ae-chem", "name": "AE Chemie"}
DEF = {
    (310, "2016.V2"): "erklären V2 Biologie",
    (310, "2016.V3"): "einen Sachverhalt nachvollziehbar machen (V3)",
    (311, "2016.V2"): "erklären V2 Chemie",
}


@pytest_asyncio.fixture
async def operatoren(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    ids = [BIO["id"], CHEM["id"]]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s) OR slug = ANY(%s)", (ids, [BIO["slug"], CHEM["slug"]]))
        for s in (BIO, CHEM):
            cur.execute("INSERT INTO subjects (id, name, slug) VALUES (%s, %s, %s)", (s["id"], s["name"], s["slug"]))
        for (fach, fassung), inhalt in DEF.items():
            cur.execute(
                "INSERT INTO context_nodes (id, category, content_type, title, content, metadata, read_scope, "
                "write_scope, status, subject_id, bp_version) VALUES (%s, 'knowledge', 'operator', 'erklären', %s, "
                "%s, 'global', 'global', 'active', %s, %s)",
                (str(uuid.uuid4()), inhalt, json.dumps({"afb": ["II"]}), fach, fassung),
            )
    conn.commit()
    yield
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", (ids,))
    conn.commit()
    conn.close()


async def _erklaeren(async_engine, stufe, subject_id=None):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    with patch("app.context.editions.load_subjects_config", return_value=FAHRPLAN), \
         patch("app.context.editions.aktuelles_schuljahr_start", return_value=2026):
        async with fabrik() as db:
            abschnitt = await aufzaehlung(
                Knotenfilter(titel=normalisiere_titel("erklären"), content_type=("operator",),
                             subject_id=subject_id),
                Suchprofil(pseudonym="ae-test", rollen=("student",), grade=stufe, aufzaehlung=50),
                db,
            )
    eigene = [t for t in abschnitt.treffer if t.get("subject_id") in (BIO["id"], CHEM["id"])]
    return abschnitt, sorted((t["subject_id"], t["bp_version"]) for t in eigene)


async def test_ohne_stufe_alle_fassungen(async_engine, operatoren):
    _, fassungen = await _erklaeren(async_engine, None)
    assert fassungen == [(310, "2016.V2"), (310, "2016.V3"), (311, "2016.V2")]


async def test_klasse_7_bekommt_v3_wo_es_sie_gibt(async_engine, operatoren):
    """Biologie V3 (gilt ab 2026/27 in Kl. 5–7); Chemie hat keine V3 → V2 (Inhalts-Fallback)."""
    _, fassungen = await _erklaeren(async_engine, 7)
    assert fassungen == [(310, "2016.V3"), (311, "2016.V2")]


async def test_klasse_9_bekommt_v2(async_engine, operatoren):
    _, fassungen = await _erklaeren(async_engine, 9)
    assert fassungen == [(310, "2016.V2"), (311, "2016.V2")]


async def test_mit_fach_genau_eine_definition(async_engine, operatoren):
    abschnitt, fassungen = await _erklaeren(async_engine, 7, subject_id=BIO["id"])
    assert fassungen == [(310, "2016.V3")]
    assert abschnitt.treffer[0]["content"] == DEF[(310, "2016.V3")]


async def test_fassung_ohne_operatoren_filtert_sie_nicht_weg(async_engine, operatoren, db_url):
    """Biologie V2 mit Kompetenzen, aber ohne Operatoren (wie auf Dev, 27.10.2026): Für Kl. 9
    gilt V2 — die Operatoren dürfen deshalb nicht verschwinden, weil V2 keine hat."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = %s AND content_type = 'operator' "
                    "AND bp_version = '2016.V2'", (BIO["id"],))
        cur.execute("INSERT INTO context_nodes (id, category, content_type, title, read_scope, write_scope, "
                    "status, subject_id, bp_version) VALUES (%s, 'knowledge', 'ik_kompetenz', 'K', 'global', "
                    "'global', 'active', %s, '2016.V2')", (str(uuid.uuid4()), BIO["id"]))
    conn.commit()
    conn.close()
    _, fassungen = await _erklaeren(async_engine, 9)
    assert (310, "2016.V3") in fassungen


async def test_gesamt_zaehlt_nach_dem_filter(async_engine, operatoren):
    """`gesamt` ist die Zahl der Bausteine, die für die Person gelten — nicht der Bestand."""
    abschnitt, _ = await _erklaeren(async_engine, 7, subject_id=BIO["id"])
    assert abschnitt.gesamt == 1 and abschnitt.vollstaendig
