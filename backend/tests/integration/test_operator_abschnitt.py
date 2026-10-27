"""Abschnitt „Operator dieser Aufgabe" (Päckchen AF, Schritt 3).

Fahrplan wie `config/subjects.yaml` (V2 in Kraft, V3 ab 2026/27 in Kl. 5–7), Schuljahr fest
2026/27 — wie `test_aufzaehlung_fassung.py`. Biologie (Kl. 5–13) hat V2 und V3, Chemie
(Kl. 8–13) nur V2 mit demselben Wortlaut für *erläutern* wie Biologie V2, Deutsch liegt
außerhalb des Kreises. Erfordert TEST_DATABASE_URL.
"""
import uuid
from unittest.mock import patch

import psycopg2
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.context import operator_abschnitt as modul
from app.context.operator_abschnitt import operator_abschnitt

pytestmark = pytest.mark.asyncio

FAHRPLAN = {"bildungsplan_default": {"bp_basis": "BP2016BW", "suffix": "", "editionen": [
    {"suffix": ""},
    {"suffix": ".V2", "ab_schuljahr": "2016/17", "einstieg_stufen": [5, 12]},
    {"suffix": ".V3", "ab_schuljahr": "2026/27", "einstieg_stufen": [5, 7], "wachstum": "nach_oben"},
]}}
FAECHER = [  # id, slug, name, min_grade, max_grade
    (320, "af-bio", "AF Biologie", 5, 13),
    (321, "af-chem", "AF Chemie", 8, 13),
    (322, "af-deutsch", "AF Deutsch", 5, 13),
]
KREIS = ["af-bio", "af-chem"]
V2_ERL = "erfassen und auf allgemeine Aussagen zurückführen und durch Beispiele verständlich machen"
KNOTEN = [  # fach, fassung, titel, inhalt
    (320, "2016.V2", "erläutern", V2_ERL),
    (320, "2016.V3", "erläutern", "veranschaulichend darstellen"),
    (320, "2016.V2", "bewerten", "nach Kriterien oder Wertebezug einschätzen"),
    (320, "2016.V3", "bewerten", "zu einem begründeten Werturteil gelangen"),
    (320, "2016.V3", "beurteilen", "ein Sachurteil fällen"),
    (321, "2016.V2", "erläutern", V2_ERL),
    (322, "2016.V2", "erläutern", "Deutsch: einen Text erläutern"),
]


@pytest_asyncio.fixture
async def daten(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    ids = [f[0] for f in FAECHER]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s) OR slug = ANY(%s)", (ids, [f[1] for f in FAECHER]))
        for f in FAECHER:
            cur.execute("INSERT INTO subjects (id, slug, name, min_grade, max_grade) VALUES (%s, %s, %s, %s, %s)", f)
        for fach, fassung, titel, inhalt in KNOTEN:
            cur.execute(
                "INSERT INTO context_nodes (id, category, content_type, title, content, read_scope, write_scope, "
                "status, subject_id, bp_version) VALUES (%s, 'knowledge', 'operator', %s, %s, 'global', 'global', "
                "'active', %s, %s)", (str(uuid.uuid4()), titel, inhalt, fach, fassung))
    conn.commit()
    modul._indizes.clear()
    yield
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", (ids,))
    conn.commit()
    conn.close()
    modul._indizes.clear()


async def _abschnitt(async_engine, nachrichten, stufe, fach=None, kreis=KREIS):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    with patch("app.context.editions.load_subjects_config", return_value=FAHRPLAN), \
         patch("app.context.editions.aktuelles_schuljahr_start", return_value=2026):
        async with fabrik() as db:
            return await operator_abschnitt(nachrichten, kreis, konversationsfach_id=fach, stufe=stufe,
                                            pseudonym="af-test", rollen=("student",), db=db)


async def test_klasse_9_fasst_gleichen_wortlaut_zusammen(async_engine, daten):
    a = await _abschnitt(async_engine, ["Erläutere die Funktion der Spaltöffnungen."], 9)
    assert a.text.splitlines() == [
        "## Operator dieser Aufgabe",
        f"erläutern (AF Biologie, AF Chemie, Fassung für Klasse 9): {V2_ERL}",
    ]
    assert a.operatoren == ["erläutern"] and a.fassungen == ["2016.V2"]


async def test_klasse_7_v3_ohne_fach_ausserhalb_der_stufe(async_engine, daten):
    """Chemie beginnt in Klasse 8 — ihre V2-Definition gehört nicht in eine 7. Klasse."""
    a = await _abschnitt(async_engine, ["Erläutere den Treibhauseffekt."], 7)
    assert a.text.splitlines()[1:] == ["erläutern (AF Biologie, Fassung für Klasse 7): veranschaulichend darstellen"]


async def test_bewerten_klasse_7_mit_abgrenzung(async_engine, daten):
    a = await _abschnitt(async_engine, ["Bewerte, ob man Wildvögel füttern sollte."], 7)
    assert a.text.splitlines()[1:] == [
        "bewerten (AF Biologie, Fassung für Klasse 7): zu einem begründeten Werturteil gelangen",
        "Abgrenzung – beurteilen (AF Biologie, Fassung für Klasse 7): ein Sachurteil fällen",
    ]


async def test_bewerten_klasse_9_ohne_abgrenzung(async_engine, daten):
    """In V2 gibt es kein *beurteilen* — keine Abgrenzung aus einer anderen Fassung."""
    a = await _abschnitt(async_engine, ["Bewerte die Kernenergie."], 9)
    assert len(a.text.splitlines()) == 2 and "Abgrenzung" not in a.text


async def test_fehlt_in_der_fassung_dann_die_neueste_mit_hinweis(async_engine, daten):
    """Lauf 19, B1: *beurteilen* gibt es nur in V3 — eine 9. Klasse (V2) bekommt die V3-Definition,
    gekennzeichnet, samt Abgrenzung aus derselben Fassung."""
    a = await _abschnitt(async_engine, ["Beurteile, ob Elektroautos umweltfreundlicher sind."], 9)
    assert a.text.splitlines()[1:] == [
        "beurteilen (AF Biologie, Fassung V3; in der Fassung für Klasse 9 kein eigener Operator): "
        "ein Sachurteil fällen",
        "Abgrenzung – bewerten (AF Biologie, Fassung V3): zu einem begründeten Werturteil gelangen",
    ]


async def test_konversationsfach_im_kreis_gilt_allein(async_engine, daten):
    a = await _abschnitt(async_engine, ["Erläutere die Elektrolyse."], 9, fach=321)
    assert a.faecher == ["AF Chemie"]


async def test_fach_ausserhalb_des_kreises_nie(async_engine, daten):
    a = await _abschnitt(async_engine, ["Erläutere das Gedicht."], 9, fach=322)
    assert "Deutsch" not in a.text


async def test_folgezug_nimmt_die_aufgabe_davor(async_engine, daten):
    a = await _abschnitt(async_engine, ["keine ahnung", "Erläutere die Spaltöffnungen."], 9)
    assert a.operatoren == ["erläutern"]


async def test_ohne_stufe_neueste_je_fach(async_engine, daten):
    a = await _abschnitt(async_engine, ["Erläutere die Osmose."], None)
    assert a.text.splitlines()[1:] == [
        "erläutern (AF Biologie, Fassung V3): veranschaulichend darstellen",
        f"erläutern (AF Chemie, Fassung V2): {V2_ERL}",
    ]


@pytest.mark.parametrize("nachrichten, kreis", [
    (["Erläutere die Spaltöffnungen."], []),        # Assistent ohne Kreis: aus
    (["Was ist eine Spaltöffnung?"], KREIS),          # kein Operator
    (["Erläutere mir die Spaltöffnungen."], KREIS),   # Bitte, keine Aufgabe (F5)
])
async def test_kein_abschnitt(async_engine, daten, nachrichten, kreis):
    assert await _abschnitt(async_engine, nachrichten, 9, kreis=kreis) is None
