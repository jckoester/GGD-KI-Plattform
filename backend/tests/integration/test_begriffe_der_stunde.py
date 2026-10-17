"""Begriffe der Stunde (0.17, Päckchen A1, Schritt 1).

`get_lesson_detail` bringt die Fachbegriffe mit, die zum Entwurf passen — aus dem Fach der
Stunde und seinen Bezugsfächern, nach Ähnlichkeit, nur was die Person lesen darf. Was schon
als Begriff in `refs` steht, steht immer vorn. Dazu: Beim Schreiben gilt als Begriff nur ein
`begriff` oder `stoffsteckbrief`, Material-Vorschläge erkennen Begriffe, und der Vektor der
Stunde folgt jedem Speichern, das seinen Eingabetext ändert.

Die Distanzen sind gesetzt wie in `test_vorab_suche_db.py`: Einheitsvektoren in einer Ebene,
die Anfrage ist die 0-Achse; `vektor_oder_none` ist durch die Attrappe ersetzt.
"""
import math
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import psycopg2
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.chat.tools import ToolContext
from app.config import settings
from app.db.models import ContextEdge, ContextNode, LessonSlot, NodeAlias
from app.planning.assistant_tools import _handle_get_lesson_detail, _handle_update_lesson_phases
from app.planning.operations import TransferPhases, apply_operations
from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

FACH, BEZUG, FREMD = 861, 862, 863
GRUPPE = 861
PRAEFIX = "A1-Begriff "
DIM = settings.embedding_dimensions


def _vektor(winkel: float) -> list[float]:
    v = [0.0] * DIM
    v[0], v[1] = math.cos(winkel), math.sin(winkel)
    return v


FRAGE = _vektor(0.0)


def _fuer_distanz(d: float) -> list[float]:
    """Ein Knotenvektor mit genau der Kosinus-Distanz ``d`` zur Anfrage."""
    return _vektor(math.acos(1.0 - d))


@pytest.fixture(scope="module")
def faecher(db_url, run_migrations):
    """Fach mit Bezugsfach, ein fremdes Fach, eine Gruppe von teacher1 — und danach weg."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    with conn.cursor() as cur:
        for sid, slug, name in ((FACH, "a1-fach", "A1 Fach"), (BEZUG, "a1-bezug", "A1 Bezug"),
                                (FREMD, "a1-fremd", "A1 Fremd")):
            cur.execute("INSERT INTO subjects (id, slug, name, sort_order) VALUES (%s, %s, %s, 0) "
                        "ON CONFLICT (id) DO NOTHING", (sid, slug, name))
        cur.execute("UPDATE subjects SET bezugsfaecher = ARRAY['a1-bezug'] WHERE id = %s", (FACH,))
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) "
                    "VALUES (%s, 'A1 9a', 'a1-9a', 'teaching_group', %s) ON CONFLICT (id) DO NOTHING",
                    (GRUPPE, FACH))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) "
                    "VALUES (%s, %s, 'teacher', 'eigen') ON CONFLICT DO NOTHING", (GRUPPE, TEACHER1_PSEUDO))
    conn.commit()
    yield conn
    with conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = %s", (GRUPPE,))
        cur.execute("DELETE FROM context_nodes WHERE title LIKE %s", (PRAEFIX + "%",))
        cur.execute("DELETE FROM groups WHERE id = %s", (GRUPPE,))
        cur.execute("DELETE FROM subjects WHERE id = ANY(%s)", ([FACH, BEZUG, FREMD],))
    conn.commit()
    conn.close()


@pytest.fixture
def aufraeumen(faecher):
    yield
    with faecher.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE read_scope_group_id = %s", (GRUPPE,))
        cur.execute("DELETE FROM context_nodes WHERE title LIKE %s", (PRAEFIX + "%",))
    faecher.commit()


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


def _ctx(db, sub=TEACHER1_PSEUDO):
    return ToolContext(db=db, user=SimpleNamespace(sub=sub), group_id=None, conversation_id=None)


async def _rufe(async_engine, handler, args, sub=TEACHER1_PSEUDO):
    async with _sitzungen(async_engine)() as db:
        return await handler(args, _ctx(db, sub))


async def _stunde(client, h, titel="Aromaten", slot_id=None, phasen=None):
    ue = (await client.post(f"/planning/groups/{GRUPPE}/units", headers=h,
                            json={"titel": "Einheit Aromaten", "farbe": 0})).json()["id"]
    rumpf = {"titel": titel} | ({"slot_id": slot_id} if slot_id else {})
    stunde = (await client.post(f"/planning/units/{ue}/lessons", headers=h, json=rumpf)).json()["id"]
    resp = await client.patch(f"/planning/lessons/{stunde}", headers=h, json={
        "stundenziel": "Mesomerie am Benzol erklären",
        "phasen": phasen or [{"name": "Einstieg", "dauer_min": 10},
                             {"name": "Erarbeitung", "dauer_min": 25, "beschreibung": "Bindungslängen"}],
    })
    assert resp.status_code == 200, resp.text
    return stunde


async def _begriff(async_engine, titel, distanz=0.1, *, fach=FACH, art="begriff", **kw):
    async with _sitzungen(async_engine)() as db:
        n = ContextNode(
            category="concept", content_type=art, title=PRAEFIX + titel, status=kw.pop("status", "active"),
            subject_id=fach, read_scope=kw.pop("read_scope", "school"),
            write_scope=kw.pop("write_scope", "school"),
            embedding=None if distanz is None else _fuer_distanz(distanz),
            metadata_=kw.pop("metadata_", {}), **kw,
        )
        db.add(n)
        await db.commit()
        return n


def _titel(eintraege):
    return [e["titel"].removeprefix(PRAEFIX) for e in eintraege]


async def _begriffe(async_engine, stunde, vektor=FRAGE):
    with patch("app.context.search.vektor_oder_none", AsyncMock(return_value=vektor)) as attrappe:
        detail = await _rufe(async_engine, _handle_get_lesson_detail, {"node_id": stunde})
    return detail["begriffe"], attrappe


# ── Auswahl ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fach_und_bezugsfach_nach_naehe(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Fach und Bezugsfach nach Distanz; das Bezugsfach trägt seinen Namen, das eigene nicht."""
    stunde = await _stunde(test_client, auth_headers)
    await _begriff(async_engine, "Mesomerie", 0.10)
    await _begriff(async_engine, "Benzol", 0.20, fach=BEZUG, art="stoffsteckbrief")
    await _begriff(async_engine, "Aromaten", 0.30, metadata_={"fassung": "Klasse 10"})

    begriffe, _ = await _begriffe(async_engine, stunde)
    assert _titel(begriffe["eintraege"]) == ["Mesomerie", "Benzol", "Aromaten"]
    mesomerie, benzol, aromaten = begriffe["eintraege"]
    assert "fach" not in mesomerie
    assert benzol["fach"] == "A1 Bezug"
    assert aromaten["fassung"] == "Klasse 10"
    assert "hinweis" not in begriffe


@pytest.mark.asyncio
async def test_was_nicht_dazugehoert(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Fremdes Fach, archiviert, fremd-privat, ohne Vektor und Nicht-Begriffe fehlen —
    auch wenn sie näher liegen als der einzige passende."""
    stunde = await _stunde(test_client, auth_headers)
    await _begriff(async_engine, "Passend", 0.40)
    await _begriff(async_engine, "Fremdes Fach", 0.01, fach=FREMD)
    await _begriff(async_engine, "Archiviert", 0.01, status="archived")
    await _begriff(async_engine, "Privat fremd", 0.01, read_scope="private", write_scope="private",
                   owner_pseudonym=TEACHER2_PSEUDO)
    await _begriff(async_engine, "Ohne Vektor", None)
    await _begriff(async_engine, "Bauteil", 0.01, art="bauteil")
    await _begriff(async_engine, "Funktion", 0.01, art="funktion")

    begriffe, _ = await _begriffe(async_engine, stunde)
    assert _titel(begriffe["eintraege"]) == ["Passend"]


@pytest.mark.asyncio
async def test_eigener_privater_begriff_kommt(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    await _begriff(async_engine, "Privat eigen", 0.10, read_scope="private", write_scope="private",
                   owner_pseudonym=TEACHER1_PSEUDO)
    begriffe, _ = await _begriffe(async_engine, stunde)
    assert _titel(begriffe["eintraege"]) == ["Privat eigen"]


@pytest.mark.asyncio
async def test_aliase_kommen_mit(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    benzol = await _begriff(async_engine, "Benzol", 0.10, art="stoffsteckbrief")
    async with _sitzungen(async_engine)() as db:
        db.add_all([NodeAlias(node_id=benzol.id, alias="Benzen"),
                    NodeAlias(node_id=benzol.id, alias="C6H6")])
        await db.commit()
    begriffe, _ = await _begriffe(async_engine, stunde)
    assert begriffe["eintraege"][0]["aliase"] == ["Benzen", "C6H6"]


@pytest.mark.asyncio
async def test_nur_die_naechsten(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    for nr, d in enumerate((0.30, 0.10, 0.20, 0.40)):
        await _begriff(async_engine, f"B{nr} {d}", d)
    with patch("app.planning.assistant_tools.BEGRIFFE_ANZAHL", 2):
        begriffe, _ = await _begriffe(async_engine, stunde)
    assert _titel(begriffe["eintraege"]) == ["B1 0.1", "B2 0.2"]


@pytest.mark.asyncio
async def test_eingetragene_stehen_immer_vorn(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Ein eingetragener Begriff kommt mit, auch weit weg — einmal, vorn, markiert."""
    stunde = await _stunde(test_client, auth_headers)
    fern = await _begriff(async_engine, "Fern", 0.90)
    await _begriff(async_engine, "Nah", 0.10)
    await _begriff(async_engine, "Mittel", 0.20)
    resp = await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers, json={
        "refs": [{"node_id": str(fern.id), "typ": "concept", "titel": fern.title}]})
    assert resp.status_code == 200, resp.text

    with patch("app.planning.assistant_tools.BEGRIFFE_ANZAHL", 2):
        begriffe, _ = await _begriffe(async_engine, stunde)
    assert _titel(begriffe["eintraege"]) == ["Fern", "Nah", "Mittel"]
    assert begriffe["eintraege"][0]["eingetragen"] is True
    assert "eingetragen" not in begriffe["eintraege"][1]


@pytest.mark.asyncio
async def test_ohne_vektor_nur_eingetragene_und_hinweis(
    test_client, auth_headers, faecher, async_engine, aufraeumen,
):
    stunde = await _stunde(test_client, auth_headers)
    drin = await _begriff(async_engine, "Drin", 0.50)
    await _begriff(async_engine, "Nah", 0.10)
    await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers, json={
        "refs": [{"node_id": str(drin.id), "typ": "concept", "titel": drin.title}]})

    begriffe, _ = await _begriffe(async_engine, stunde, vektor=None)
    assert _titel(begriffe["eintraege"]) == ["Drin"]
    assert "search_context_nodes" in begriffe["hinweis"]


@pytest.mark.asyncio
async def test_vergleich_mit_dem_entwurf(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Verglichen wird der Entwurf, wie er gerade ist — nicht der gespeicherte Vektor."""
    stunde = await _stunde(test_client, auth_headers, titel="Delokalisierte Elektronen")
    _, attrappe = await _begriffe(async_engine, stunde)
    text = attrappe.await_args.args[0]
    for teil in ("Delokalisierte Elektronen", "Mesomerie am Benzol erklären", "Erarbeitung",
                 "Bindungslängen", "Einheit Aromaten"):
        assert teil in text, text


# ── Schreiben: was ein Begriff ist ───────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("art, gilt", [
    ("begriff", True), ("stoffsteckbrief", True), ("bauteil", False), ("funktion", False),
])
async def test_begriff_beim_schreiben(test_client, auth_headers, faecher, async_engine, aufraeumen, art, gilt):
    stunde = await _stunde(test_client, auth_headers)
    knoten = await _begriff(async_engine, f"Art {art}", 0.10, art=art)
    aus = await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}],
        "refs": [{"node_id": str(knoten.id), "typ": "concept", "titel": "Vom Modell", "code": "X"}],
    })
    if not gilt:
        # Kein passender Begriff: nicht eingetragen, gemeldet — der Aufruf selbst gelingt.
        assert aus.get("ok") is True and aus.get("nicht_eingetragen"), aus
        refs = (await test_client.get(f"/planning/lessons/{stunde}", headers=auth_headers)).json()["refs"]
        assert refs == []
        return
    assert aus.get("ok") is True, aus
    refs = (await test_client.get(f"/planning/lessons/{stunde}", headers=auth_headers)).json()["refs"]
    # Titel und Bausteinart aus dem Knoten; ein Begriff hat keine Nummer — die des Modells
    # fällt weg.
    assert refs == [{"node_id": str(knoten.id), "typ": "concept", "code": None,
                     "titel": knoten.title, "partiell": False, "content_type": art}]


# ── Begriffe über den Titel (Messung 1, Plan § 16 A1) ────────────────────────
#
# Die Suchwerkzeuge geben keine Kennungen; das Modell trägt Begriffe über ihren Titel ein.


async def _schreibe_begriffe(async_engine, stunde, *refs):
    return await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}], "refs": list(refs)})


async def _refs(client, h, stunde):
    return (await client.get(f"/planning/lessons/{stunde}", headers=h)).json()["refs"]


@pytest.mark.asyncio
async def test_begriff_ueber_titel_und_alias(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    meso = await _begriff(async_engine, "Mesomerie")
    benzol = await _begriff(async_engine, "Benzol", fach=BEZUG, art="stoffsteckbrief")
    async with _sitzungen(async_engine)() as db:
        db.add(NodeAlias(node_id=meso.id, alias="Resonanz"))
        await db.commit()

    aus = await _schreibe_begriffe(
        async_engine, stunde,
        {"typ": "concept", "titel": "a1-begriff  MESOMERIE"},     # Normalisierung wie die Namenssuche
        {"typ": "concept", "titel": PRAEFIX + "Benzol"},          # aus dem Bezugsfach
        {"typ": "concept", "titel": "Resonanz"},                   # Alias → derselbe, entfällt doppelt
    )
    assert aus.get("ok") is True and "nicht_eingetragen" not in aus, aus
    assert [(r["node_id"], r["content_type"]) for r in await _refs(test_client, auth_headers, stunde)] == [
        (str(meso.id), "begriff"), (str(benzol.id), "stoffsteckbrief")]


@pytest.mark.asyncio
async def test_geschuetzter_bindestrich(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Messung 3: Das Modell schreibt „Arenium‑Ion" mit U+2011 — der Alias heißt „Arenium-Ion"."""
    stunde = await _stunde(test_client, auth_headers)
    sub = await _begriff(async_engine, "elektrophile Substitution")
    async with _sitzungen(async_engine)() as db:
        db.add(NodeAlias(node_id=sub.id, alias="Arenium-Ion"))
        await db.commit()
    aus = await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": "Arenium\u2011Ion"},
                                   {"typ": "concept", "titel": "Areni\u00adum\u2010Ion"})
    assert "nicht_eingetragen" not in aus, aus
    assert [r["node_id"] for r in await _refs(test_client, auth_headers, stunde)] == [str(sub.id)]


# ── Aliase als Namen der Stunde (Messung 9, Plan § 26) ───────────────────────
#
# Viele Aliase im Speicher sind Unterbegriffe: „σ-Komplex" bei „elektrophile Substitution".
# Ein Eintrag je Knoten; die Aliase, unter denen die Stunde ihn nennt, stehen dabei.


async def _substitution(async_engine, *aliase):
    sub = await _begriff(async_engine, "elektrophile Substitution")
    async with _sitzungen(async_engine)() as db:
        db.add_all(NodeAlias(node_id=sub.id, alias=a) for a in aliase)
        await db.commit()
    return sub


@pytest.mark.asyncio
async def test_alias_bleibt_als_name_sichtbar(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    sub = await _substitution(async_engine, "σ-Komplex", "Arenium-Ion", "π-Komplex")
    aus = await _schreibe_begriffe(
        async_engine, stunde,
        {"typ": "concept", "titel": "σ‑Komplex"},            # Schreibweise des Modells …
        {"typ": "concept", "titel": "Arenium-Ion"},
        {"typ": "concept", "titel": PRAEFIX + "elektrophile Substitution"},
    )
    titel = PRAEFIX + "elektrophile Substitution"
    # … gespeichert wird die des Speichers; ein Eintrag, der Titel selbst ist kein Alias.
    assert aus["eingetragen"] == [{"titel": titel, "aliase": ["σ-Komplex", "Arenium-Ion"]}], aus
    refs = await _refs(test_client, auth_headers, stunde)
    assert [(r["node_id"], r["titel"], r["aliase"]) for r in refs] == [
        (str(sub.id), titel, ["σ-Komplex", "Arenium-Ion"])]


@pytest.mark.asyncio
async def test_unter_dem_titel_ohne_aliase(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    await _substitution(async_engine, "σ-Komplex")
    aus = await _schreibe_begriffe(async_engine, stunde,
                                   {"typ": "concept", "titel": PRAEFIX + "elektrophile Substitution"})
    assert aus["eingetragen"] == [{"titel": PRAEFIX + "elektrophile Substitution"}], aus
    assert "aliase" not in (await _refs(test_client, auth_headers, stunde))[0]


@pytest.mark.asyncio
async def test_aliase_bleiben_beim_neuschreiben(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Das Modell schickt `refs` als ganze Liste und lässt `aliase` leicht weg. Einen Alias,
    den es dem Knoten nur zuschreibt, gibt es nicht — er fällt heraus."""
    stunde = await _stunde(test_client, auth_headers)
    sub = await _substitution(async_engine, "σ-Komplex", "π-Komplex")
    await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": "σ-Komplex"})
    aus = await _schreibe_begriffe(
        async_engine, stunde,
        {"typ": "concept", "node_id": str(sub.id), "titel": PRAEFIX + "elektrophile Substitution",
         "aliase": ["Wheland-Komplex"]},
        {"typ": "concept", "titel": "π-Komplex"},
    )
    assert aus["eingetragen"] == [{"titel": PRAEFIX + "elektrophile Substitution",
                                   "aliase": ["σ-Komplex", "π-Komplex"]}], aus


@pytest.mark.asyncio
async def test_mehrzahl_trifft_die_einzahl(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """M9–M11: „Blattfarbstoffe" fiel durch, der Alias heißt „Blattfarbstoff". Gespeichert wird
    der Alias in seiner Schreibweise; die Mehrzahl des Titels ist kein Alias."""
    stunde = await _stunde(test_client, auth_headers)
    chl = await _begriff(async_engine, "Chlorophyll", fach=BEZUG)
    kat = await _begriff(async_engine, "Katalysator")
    async with _sitzungen(async_engine)() as db:
        db.add(NodeAlias(node_id=chl.id, alias="Blattfarbstoff"))
        await db.commit()
    aus = await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": "Blattfarbstoffe"},
                                   {"typ": "concept", "titel": PRAEFIX + "Katalysatoren"})
    assert "nicht_eingetragen" not in aus, aus
    assert aus["eingetragen"] == [{"titel": PRAEFIX + "Chlorophyll", "aliase": ["Blattfarbstoff"]},
                                  {"titel": PRAEFIX + "Katalysator"}]
    assert [r["node_id"] for r in await _refs(test_client, auth_headers, stunde)] == [str(chl.id), str(kat.id)]


@pytest.mark.asyncio
async def test_mehrzahl_nur_bei_einem_treffer(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """„Phasen" passt auf „Phas" und auf „Phase" — dann lieber nicht eintragen als raten."""
    stunde = await _stunde(test_client, auth_headers)
    await _begriff(async_engine, "Phase")
    await _begriff(async_engine, "Phas")
    aus = await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": PRAEFIX + "Phasen"})
    assert [n["titel"] for n in aus["nicht_eingetragen"]] == [PRAEFIX + "Phasen"], aus
    assert await _refs(test_client, auth_headers, stunde) == []


@pytest.mark.asyncio
async def test_aliase_in_der_auswahl_und_im_planer(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """`begriffe` zeigt eingetragene mit ihren Aliasen; der Planer speichert sie mit."""
    stunde = await _stunde(test_client, auth_headers)
    await _substitution(async_engine, "σ-Komplex")
    await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": "σ-Komplex"})
    begriffe, _ = await _begriffe(async_engine, stunde)
    assert begriffe["eintraege"][0] == {"titel": PRAEFIX + "elektrophile Substitution",
                                        "eingetragen": True, "aliase": ["σ-Komplex"]}
    refs = await _refs(test_client, auth_headers, stunde)
    resp = await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers,
                                   json={"refs": refs, "stundenziel": "anders"})
    assert resp.status_code == 200, resp.text
    assert (await _refs(test_client, auth_headers, stunde))[0]["aliase"] == ["σ-Komplex"]


@pytest.mark.asyncio
async def test_fehlender_begriff_wird_gemeldet(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Fehlt einer, wird der Rest gespeichert — Phasen und vorhandene Begriffe."""
    stunde = await _stunde(test_client, auth_headers)
    kat = await _begriff(async_engine, "Katalysator")
    await _begriff(async_engine, "Lewis-Schreibweise")
    aus = await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": PRAEFIX + "Katalysator"},
                                   {"typ": "concept", "titel": PRAEFIX + "Lewis-Säure"})
    assert aus.get("ok") is True, aus
    assert [n["titel"] for n in aus["nicht_eingetragen"]] == [PRAEFIX + "Lewis-Säure"]
    assert "Fachschaft" in aus["nicht_eingetragen"][0]["grund"]
    assert [r["node_id"] for r in await _refs(test_client, auth_headers, stunde)] == [str(kat.id)]
    phasen = (await test_client.get(f"/planning/lessons/{stunde}", headers=auth_headers)).json()["phasen"]
    assert [p["name"] for p in phasen] == ["Neu"]


@pytest.mark.asyncio
async def test_titel_findet_nichts_ausserhalb(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Fremdes Fach, archiviert, fremd-privat, Bauteil: über den Titel nicht erreichbar."""
    stunde = await _stunde(test_client, auth_headers)
    await _begriff(async_engine, "Fremd", fach=FREMD)
    await _begriff(async_engine, "Archiv", status="archived")
    await _begriff(async_engine, "Privat", read_scope="private", write_scope="private",
                   owner_pseudonym=TEACHER2_PSEUDO)
    await _begriff(async_engine, "Bauteil", art="bauteil")
    aus = await _schreibe_begriffe(async_engine, stunde, *(
        {"typ": "concept", "titel": PRAEFIX + t} for t in ("Fremd", "Archiv", "Privat", "Bauteil")))
    assert len(aus["nicht_eingetragen"]) == 4, aus
    assert await _refs(test_client, auth_headers, stunde) == []


@pytest.mark.asyncio
async def test_gleichnamige_fassungen(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    await _begriff(async_engine, "Oxidation", metadata_={"fassung": "Sauerstoffaufnahme"})
    abgabe = await _begriff(async_engine, "Oxidation", metadata_={"fassung": "Elektronenabgabe"})
    ohne = await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": PRAEFIX + "Oxidation"})
    grund = ohne["nicht_eingetragen"][0]["grund"]
    assert "Elektronenabgabe" in grund and "Sauerstoffaufnahme" in grund
    mit = await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": PRAEFIX + "Oxidation",
                                                          "fassung": "elektronenabgabe"})
    assert "nicht_eingetragen" not in mit, mit
    assert [r["node_id"] for r in await _refs(test_client, auth_headers, stunde)] == [str(abgabe.id)]


@pytest.mark.asyncio
async def test_eigenes_fach_vor_bezugsfach(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    eigen = await _begriff(async_engine, "Energie")
    await _begriff(async_engine, "Energie", fach=BEZUG)
    aus = await _schreibe_begriffe(async_engine, stunde, {"typ": "concept", "titel": PRAEFIX + "Energie"})
    assert "nicht_eingetragen" not in aus, aus
    assert [r["node_id"] for r in await _refs(test_client, auth_headers, stunde)] == [str(eigen.id)]


@pytest.mark.asyncio
async def test_begriffe_ohne_kennungen_mit_anleitung(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """`begriffe` trägt keine Kennungen mehr, aber die Anleitung zum Absatz."""
    stunde = await _stunde(test_client, auth_headers)
    await _begriff(async_engine, "Mesomerie")
    begriffe, _ = await _begriffe(async_engine, stunde)
    assert all("node_id" not in e for e in begriffe["eintraege"])
    assert "Begriffe dieser Stunde" in begriffe["anleitung"]
    assert "nicht beim Kürzen" in begriffe["anleitung"]
    assert "aus allen Phasen" in begriffe["anleitung"]


@pytest.mark.asyncio
async def test_material_schlaegt_begriffe_vor(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Ein Arbeitsblatt, das auf einen Begriff verweist, schlägt ihn als `concept` vor."""
    stunde = await _stunde(test_client, auth_headers)
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    async with _sitzungen(async_engine)() as db:
        blatt = ContextNode(category="artifact", content_type="arbeitsblatt", title=PRAEFIX + "AB",
                            status="active", read_scope="school", write_scope="private",
                            owner_pseudonym=TEACHER1_PSEUDO, metadata_={})
        db.add(blatt)
        await db.flush()
        db.add(ContextEdge(from_node_id=blatt.id, to_node_id=begriff.id, relation="references"))
        await db.commit()

    aus = await _rufe(async_engine, _handle_update_lesson_phases, {"node_id": stunde, "phasen": [
        {"name": "Erarbeitung", "dauer_min": 20,
         "material": [{"typ": "node", "node_id": str(blatt.id), "titel": "AB"}]},
    ]})
    assert aus.get("ok") is True, aus
    assert [(v["node_id"], v["typ"]) for v in aus["suggested_refs"]] == [(str(begriff.id), "concept")]


# ── Der Vektor der Stunde folgt dem Speichern ────────────────────────────────


async def _vektor_setzen(async_engine, stunde):
    async with _sitzungen(async_engine)() as db:
        n = await db.get(ContextNode, UUID(stunde))
        n.embedding = _fuer_distanz(0.3)
        await db.commit()


async def _hat_vektor(async_engine, stunde) -> bool:
    async with _sitzungen(async_engine)() as db:
        return (await db.get(ContextNode, UUID(stunde))).embedding is not None


@pytest.mark.asyncio
async def test_planer_refs_verwerfen_den_vektor(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    await _vektor_setzen(async_engine, stunde)

    with patch("app.planning.router.enqueue_embedding_job", AsyncMock()) as einbetten:
        # Nur Phasen: Die stehen nicht im Vektor — kein Modellaufruf.
        await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers,
                                json={"phasen": [{"name": "Nur Phasen", "dauer_min": 45}]})
        assert await _hat_vektor(async_engine, stunde)
        einbetten.assert_not_awaited()

        await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers, json={
            "refs": [{"node_id": str(begriff.id), "typ": "concept", "titel": begriff.title}]})
    assert not await _hat_vektor(async_engine, stunde)
    einbetten.assert_awaited_once()
    assert einbetten.await_args.args[0] == UUID(stunde)


@pytest.mark.asyncio
async def test_planer_titel_verwirft_den_vektor(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers, json={
        "refs": [{"node_id": str(begriff.id), "typ": "concept", "titel": begriff.title}]})
    await _vektor_setzen(async_engine, stunde)
    await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers, json={"titel": "Neuer Titel"})
    assert not await _hat_vektor(async_engine, stunde)


@pytest.mark.asyncio
async def test_assistent_refs_verwerfen_den_vektor(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers)
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    await _vektor_setzen(async_engine, stunde)

    with patch("app.planning.assistant_tools.enqueue_embedding_job", AsyncMock()) as einbetten:
        await _rufe(async_engine, _handle_update_lesson_phases, {
            "node_id": stunde, "phasen": [{"name": "Nur Phasen", "dauer_min": 45}]})
        assert await _hat_vektor(async_engine, stunde)
        await _rufe(async_engine, _handle_update_lesson_phases, {
            "node_id": stunde, "phasen": [{"name": "Nur Phasen", "dauer_min": 45}],
            "refs": [{"node_id": str(begriff.id), "typ": "concept"}]})
    assert not await _hat_vektor(async_engine, stunde)
    einbetten.assert_awaited_once()


async def _termin(async_engine, tag: int) -> str:
    async with _sitzungen(async_engine)() as db:
        slot = LessonSlot(group_id=GRUPPE, date=date(2026, 10, tag), start_period=1, periods=1, halbjahr=1)
        db.add(slot)
        await db.commit()
        return str(slot.id)


@pytest.mark.asyncio
async def test_reflexion_und_rueckgaengig_verwerfen_den_vektor(
    test_client, auth_headers, faecher, async_engine, aufraeumen,
):
    slot = await _termin(async_engine, 5)
    stunde = await _stunde(test_client, auth_headers, slot_id=slot)
    await _vektor_setzen(async_engine, stunde)

    with patch("app.planning.review_service.enqueue_embedding_job", AsyncMock()) as einbetten:
        resp = await test_client.post(f"/planning/slots/{slot}/review", headers=auth_headers,
                                      json={"phasen_status": {}, "reflexion": "Benzol-Modell trug gut"})
        assert resp.status_code == 200, resp.text
        assert not await _hat_vektor(async_engine, stunde)
        assert einbetten.await_count == 1

        await _vektor_setzen(async_engine, stunde)
        resp = await test_client.delete(f"/planning/slots/{slot}/review", headers=auth_headers)
        assert resp.status_code == 200, resp.text
    assert not await _hat_vektor(async_engine, stunde)
    assert einbetten.await_count == 2


@pytest.mark.asyncio
async def test_nachbereitung_ohne_reflexion_laesst_den_vektor(
    test_client, auth_headers, faecher, async_engine, aufraeumen,
):
    """Die Auto-Nachbereitung schickt keine Reflexion — sie kostet keinen Modellaufruf."""
    slot = await _termin(async_engine, 6)
    stunde = await _stunde(test_client, auth_headers, slot_id=slot)
    await _vektor_setzen(async_engine, stunde)
    resp = await test_client.post(f"/planning/slots/{slot}/review", headers=auth_headers,
                                  json={"phasen_status": {}})
    assert resp.status_code == 200, resp.text
    assert await _hat_vektor(async_engine, stunde)


@pytest.mark.asyncio
async def test_uebertragung_traegt_den_begriff_als_begriff(
    test_client, auth_headers, faecher, async_engine, aufraeumen,
):
    """Ein offener Begriff wandert als Begriff in die Folgestunde — mit Titel —, und deren
    Vektor wird verworfen. Bis 0.17 kam er dort als `{"node_id", "typ": "ik"}` an."""
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    quelle_slot, ziel_slot = await _termin(async_engine, 7), await _termin(async_engine, 8)
    quelle = await _stunde(test_client, auth_headers, titel="Quelle", slot_id=quelle_slot)
    ziel = await _stunde(test_client, auth_headers, titel="Ziel", slot_id=ziel_slot)
    ref = {"node_id": str(begriff.id), "typ": "concept", "titel": begriff.title, "partiell": False}
    await test_client.patch(f"/planning/lessons/{quelle}", headers=auth_headers, json={"refs": [ref]})
    gespeichert = (await test_client.get(f"/planning/lessons/{quelle}", headers=auth_headers)).json()
    phasen = gespeichert["phasen"]
    erarbeitung = next(p["id"] for p in phasen if p["name"] == "Erarbeitung")
    resp = await test_client.post(f"/planning/slots/{quelle_slot}/review", headers=auth_headers, json={
        "phasen_status": {erarbeitung: "offen"}, "refs_offen": [str(begriff.id)]})
    assert resp.status_code == 200, resp.text
    await _vektor_setzen(async_engine, ziel)

    async with _sitzungen(async_engine)() as db:
        ergebnis = await apply_operations(db, GRUPPE, [TransferPhases(
            op="transfer_phases", from_lesson_id=quelle, to_lesson_id=ziel, phase_ids=[erarbeitung])],
            summary="Erarbeitung übertragen")
    assert not ergebnis.errors
    refs = (await test_client.get(f"/planning/lessons/{ziel}", headers=auth_headers)).json()["refs"]
    assert refs == gespeichert["refs"]
    assert refs[0]["typ"] == "concept" and refs[0]["titel"] == begriff.title
    assert not await _hat_vektor(async_engine, ziel)


@pytest.mark.asyncio
async def test_einheit_titel_verwirft_ihren_vektor(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Dieselbe Lücke bei der Einheit: Ihr Titel steht im Vektor, die Farbe nicht."""
    ue = (await test_client.post(f"/planning/groups/{GRUPPE}/units", headers=auth_headers,
                                 json={"titel": "Aromaten", "farbe": 0})).json()["id"]
    async with _sitzungen(async_engine)() as db:
        n = await db.get(ContextNode, UUID(ue))
        n.metadata_ = {**n.metadata_, "refs": [{"node_id": str(n.id), "typ": "ik", "titel": "3.3.1(1) Aromaten"}]}
        await db.commit()
    await _vektor_setzen(async_engine, ue)

    with patch("app.planning.service.enqueue_embedding_job", AsyncMock()) as einbetten:
        resp = await test_client.patch(f"/planning/groups/{GRUPPE}/units/{ue}", headers=auth_headers,
                                       json={"farbe": 3})
        assert resp.status_code == 200, resp.text
        assert await _hat_vektor(async_engine, ue)
        einbetten.assert_not_awaited()

        resp = await test_client.patch(f"/planning/groups/{GRUPPE}/units/{ue}", headers=auth_headers,
                                       json={"titel": "Aromaten und Benzol"})
        assert resp.status_code == 200, resp.text
    assert not await _hat_vektor(async_engine, ue)
    einbetten.assert_awaited_once()


# ── „Rückgängig" nimmt die ganze Stunde zurück ───────────────────────────────
#
# Bis 0.17 stellte ein Snapshot nur Phasen wieder her, und nur die von Stunden, die Phasen
# hatten. Schrieb der Assistent Begriffe, nahm „Rückgängig" sie nicht zurück.


async def _neuester_snapshot(client, h, grund):
    snaps = (await client.get(f"/planning/groups/{GRUPPE}/snapshots", headers=h)).json()
    return next(s["id"] for s in snaps if s["reason"] == grund)


async def _entwurf(client, h, stunde):
    return (await client.get(f"/planning/lessons/{stunde}", headers=h)).json()


@pytest.mark.asyncio
async def test_rueckgaengig_nimmt_begriffe_und_stundenziel_zurueck(
    test_client, auth_headers, faecher, async_engine, aufraeumen,
):
    stunde = await _stunde(test_client, auth_headers, slot_id=await _termin(async_engine, 12))
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    vorher = await _entwurf(test_client, auth_headers, stunde)

    aus = await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}], "stundenziel": "Anderes Ziel",
        "refs": [{"node_id": str(begriff.id), "typ": "concept"}]})
    assert aus.get("ok") is True, aus
    await _vektor_setzen(async_engine, stunde)

    snap = await _neuester_snapshot(test_client, auth_headers, "assistant")
    with patch("app.planning.snapshots.enqueue_embedding_job", AsyncMock()) as einbetten:
        resp = await test_client.post(f"/planning/snapshots/{snap}/restore", headers=auth_headers)
        assert resp.status_code == 200, resp.text
    nachher = await _entwurf(test_client, auth_headers, stunde)
    assert nachher["refs"] == vorher["refs"] == []
    assert nachher["stundenziel"] == vorher["stundenziel"]
    assert [p["name"] for p in nachher["phasen"]] == [p["name"] for p in vorher["phasen"]]
    # Die Begriffe sind aus dem Vektor heraus — er wird verworfen und neu gebildet.
    assert not await _hat_vektor(async_engine, stunde)
    einbetten.assert_awaited_once()


@pytest.mark.asyncio
async def test_rueckgaengig_nimmt_den_titel_zurueck(test_client, auth_headers, faecher, async_engine, aufraeumen):
    stunde = await _stunde(test_client, auth_headers, titel="Alter Titel", slot_id=await _termin(async_engine, 13))
    resp = await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers, json={"titel": "Neuer Titel"})
    assert resp.status_code == 200, resp.text
    snap = await _neuester_snapshot(test_client, auth_headers, "edit")
    await test_client.post(f"/planning/snapshots/{snap}/restore", headers=auth_headers)
    assert (await _entwurf(test_client, auth_headers, stunde))["titel"] == "Alter Titel"


@pytest.mark.asyncio
async def test_rueckgaengig_leert_eine_leere_stunde_wieder(
    test_client, auth_headers, faecher, async_engine, aufraeumen,
):
    """Eine Stunde ohne Phasen bekommt welche — „Rückgängig" macht sie wieder leer."""
    slot = await _termin(async_engine, 14)
    ue = (await test_client.post(f"/planning/groups/{GRUPPE}/units", headers=auth_headers,
                                 json={"titel": "Leer", "farbe": 0})).json()["id"]
    stunde = (await test_client.post(f"/planning/units/{ue}/lessons", headers=auth_headers,
                                     json={"titel": "Leer", "slot_id": slot})).json()["id"]
    assert (await _entwurf(test_client, auth_headers, stunde))["phasen"] == []

    await _rufe(async_engine, _handle_update_lesson_phases, {
        "node_id": stunde, "phasen": [{"name": "Neu", "dauer_min": 45}]})
    snap = await _neuester_snapshot(test_client, auth_headers, "assistant")
    await test_client.post(f"/planning/snapshots/{snap}/restore", headers=auth_headers)
    assert (await _entwurf(test_client, auth_headers, stunde))["phasen"] == []


@pytest.mark.asyncio
async def test_alter_snapshot_laesst_begriffe_stehen(test_client, auth_headers, faecher, async_engine, aufraeumen):
    """Ein Snapshot von vor 0.17 kennt nur Phasen — `refs` und Titel bleiben, wie sie sind."""
    from app.db.models import SlotPlanSnapshot

    stunde = await _stunde(test_client, auth_headers, slot_id=await _termin(async_engine, 15))
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    await test_client.patch(f"/planning/lessons/{stunde}", headers=auth_headers, json={
        "refs": [{"node_id": str(begriff.id), "typ": "concept", "titel": begriff.title}]})
    async with _sitzungen(async_engine)() as db:
        alt = SlotPlanSnapshot(group_id=GRUPPE, reason="edit", payload={
            "slots": [], "stunden_phasen": {stunde: [{"id": "p-alt", "name": "Alt", "dauer_min": 45}]}})
        db.add(alt)
        await db.commit()
    await test_client.post(f"/planning/snapshots/{alt.id}/restore", headers=auth_headers)
    nachher = await _entwurf(test_client, auth_headers, stunde)
    assert [p["name"] for p in nachher["phasen"]] == ["Alt"]
    assert [r["node_id"] for r in nachher["refs"]] == [str(begriff.id)]
    assert nachher["titel"] == "Aromaten"


@pytest.mark.asyncio
async def test_rueckgaengig_einer_uebertragung_nimmt_die_refs_mit(
    test_client, auth_headers, faecher, async_engine, aufraeumen,
):
    begriff = await _begriff(async_engine, "Mesomerie", 0.10)
    quelle_slot, ziel_slot = await _termin(async_engine, 19), await _termin(async_engine, 20)
    quelle = await _stunde(test_client, auth_headers, titel="Quelle", slot_id=quelle_slot)
    ziel = await _stunde(test_client, auth_headers, titel="Ziel", slot_id=ziel_slot)
    await test_client.patch(f"/planning/lessons/{quelle}", headers=auth_headers, json={
        "refs": [{"node_id": str(begriff.id), "typ": "concept", "titel": begriff.title}]})
    erarbeitung = next(p["id"] for p in (await _entwurf(test_client, auth_headers, quelle))["phasen"]
                       if p["name"] == "Erarbeitung")
    await test_client.post(f"/planning/slots/{quelle_slot}/review", headers=auth_headers, json={
        "phasen_status": {erarbeitung: "offen"}, "refs_offen": [str(begriff.id)]})
    async with _sitzungen(async_engine)() as db:
        ergebnis = await apply_operations(db, GRUPPE, [TransferPhases(
            op="transfer_phases", from_lesson_id=quelle, to_lesson_id=ziel, phase_ids=[erarbeitung])],
            summary="Erarbeitung übertragen")
    assert (await _entwurf(test_client, auth_headers, ziel))["refs"] != []

    await test_client.post(f"/planning/snapshots/{ergebnis.snapshot_id}/restore", headers=auth_headers)
    nachher = await _entwurf(test_client, auth_headers, ziel)
    assert nachher["refs"] == []
    assert [p["name"] for p in nachher["phasen"]] == ["Einstieg", "Erarbeitung"]
    # Und die Quelle führt den Begriff wieder als offen.
    async with _sitzungen(async_engine)() as db:
        assert (await db.get(ContextNode, UUID(quelle))).metadata_["refs_offen"] == [str(begriff.id)]


# ── Die Suche der Leiste: Fach samt Bezugsfächern (Schritt 3) ────────────────


@pytest.mark.asyncio
async def test_knotenliste_mit_bezugsfaechern(test_client, auth_headers, faecher, async_engine, aufraeumen):
    await _begriff(async_engine, "Eigen")
    await _begriff(async_engine, "Bezug", fach=BEZUG, art="stoffsteckbrief")
    await _begriff(async_engine, "Fremd", fach=FREMD)
    await _begriff(async_engine, "Privat fremd", read_scope="private", write_scope="private",
                   owner_pseudonym=TEACHER2_PSEUDO)

    async def titel(**params):
        resp = await test_client.get("/context/nodes", headers=auth_headers, params={
            "q": PRAEFIX, "content_type": ["begriff", "stoffsteckbrief"], **params})
        assert resp.status_code == 200, resp.text
        return sorted(n["title"].removeprefix(PRAEFIX) for n in resp.json())

    assert await titel(subject_id=FACH, mit_bezugsfaechern="true") == ["Bezug", "Eigen"]
    # Ohne den Schalter wie bisher nur das Fach selbst.
    assert await titel(subject_id=FACH) == ["Eigen"]
    # Bezugsfächer sind gerichtet: Das Bezugsfach liest das Fach nicht mit.
    assert await titel(subject_id=BEZUG, mit_bezugsfaechern="true") == ["Bezug"]

