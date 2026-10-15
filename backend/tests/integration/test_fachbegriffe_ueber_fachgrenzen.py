"""Fachbegriffe über Fachgrenzen (0.16, Plan „Vorab-Suche-Begriffe" F6 und F7).

**F6 — Verweise:** Ein Wikilink findet sein Ziel im eigenen Fach, dann über eine Kennung in
jedem Fach, zuletzt in den Bezugsfächern. Mehrdeutig heißt: keine Kante.

**F7 — Dubletten:** Einen Begriff, den ein anderes Fach schon führt, gibt es nur mit
Abgrenzung — im Import wie im Editor. Was vor 0.16 kollidierte, blockiert nichts.

⚠️ **Eindeutige Namen.** Die Kollisionsprüfung läuft über alle Fächer der Datenbank; ein
„Fotosynthese" aus einem anderen Test fände sich sonst mit.
"""
import json
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.context import fachbegriffe_import as seed
from app.context.fachbegriffe_import import leite_id_ab
from app.context.fachbegriffe_kollision import bestand, kollisionen
from app.db.models import ContextEdge, ContextNode, NodeAlias, Subject

pytestmark = pytest.mark.asyncio

TOKEN = uuid.uuid4().hex[:6]
SYNTHESE = f"Quarksynthese{TOKEN}"
ZELLE = f"Grünzelle{TOKEN}"
ENERGIE = f"Wuchtenergie{TOKEN}"
OSMOSE = f"Saftosmose{TOKEN}"


def _md(titel: str, fach: str, *, kennung: str = "", aliase=(), abgrenzung=(),
        verwandt=()) -> bytes:
    kopf = f"id: {kennung}\n" if kennung else ""
    if aliase:
        kopf += f"aliase: {json.dumps(list(aliase), ensure_ascii=False)}\n"
    if verwandt:
        kopf += f"verwandt: {json.dumps([f'[[{z}]]' for z in verwandt], ensure_ascii=False)}\n"
    text = (f"---\nknotentyp: begriff\n{kopf}titel: {titel}\nfach: {fach}\n---\n\n"
            f"## Definition\n\nEin Text über {titel}.\n")
    if abgrenzung:
        text += "\n## Abgrenzung\n\n" + "".join(f"- [[{z}]] – anders gemeint\n" for z in abgrenzung)
    return text.encode("utf-8")


async def _fach(db, name: str, code: str, bezug=()) -> Subject:
    fach = Subject(slug=f"{name.lower()}-{TOKEN}-{uuid.uuid4().hex[:4]}", name=f"{name} {TOKEN}",
                   fach_code=code, bezugsfaecher=list(bezug))
    db.add(fach)
    await db.flush()
    return fach


@pytest_asyncio.fixture
async def faecher(db_session):
    """Biologie und Chemie, NwT mit beiden als Bezugsfach, ein Fach ohne Bezug."""
    bio = await _fach(db_session, "Bio", f"B{TOKEN[:3]}".upper())
    chemie = await _fach(db_session, "Chemie", f"C{TOKEN[:3]}".upper())
    fremd = await _fach(db_session, "Fremd", f"F{TOKEN[:3]}".upper())
    nwt = await _fach(db_session, "NwT", f"N{TOKEN[:3]}".upper(), bezug=[bio.slug, chemie.slug])
    return {"bio": bio, "chemie": chemie, "fremd": fremd, "nwt": nwt}


async def _import(db, dateien: dict[str, bytes]):
    bilanz = await seed.importiere(db, dateien, ohne_fachschaft=True)
    await db.flush()
    return bilanz


async def _knoten(db, titel: str, fach: Subject) -> ContextNode | None:
    return (await db.execute(sa.select(ContextNode).where(
        ContextNode.title == titel, ContextNode.subject_id == fach.id))).scalars().first()


async def _kanten(db, von: ContextNode) -> list[tuple[str, int, dict]]:
    zeilen = (await db.execute(
        sa.select(ContextNode.title, ContextNode.subject_id, ContextEdge.metadata_)
        .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
        .where(ContextEdge.from_node_id == von.id)
    )).all()
    return [(t, s, m) for t, s, m in zeilen]


class TestVerweiseUeberFachgrenzen:
    async def test_ziel_im_bezugsfach_wird_gefunden_und_gemeldet(self, db_session, faecher):
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        bilanz = await _import(db_session, {"Blatt.md": _md(f"Blatt{TOKEN}", nwt.slug,
                                                              verwandt=[SYNTHESE])})
        blatt = await _knoten(db_session, f"Blatt{TOKEN}", nwt)
        assert [(t, s) for t, s, _ in await _kanten(db_session, blatt)] == [(SYNTHESE, bio.id)]
        assert bilanz.ueber_fachgrenzen == {f"{SYNTHESE} ({bio.name})": 1}
        assert SYNTHESE not in bilanz.offene_ziele

    async def test_eigenes_fach_vor_bezugsfach(self, db_session, faecher):
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{ZELLE}.md": _md(ZELLE, bio.slug)})
        await _import(db_session, {f"{ZELLE}.md": _md(ZELLE, nwt.slug, abgrenzung=[
            leite_id_ab(bio.fach_code, ZELLE)])})
        bilanz = await _import(db_session, {"Blatt.md": _md(f"Blatt{TOKEN}", nwt.slug,
                                                              verwandt=[ZELLE])})
        blatt = await _knoten(db_session, f"Blatt{TOKEN}", nwt)
        assert [(t, s) for t, s, _ in await _kanten(db_session, blatt)] == [(ZELLE, nwt.id)]
        assert bilanz.ueber_fachgrenzen == {}

    async def test_gleichnamig_in_zwei_bezugsfaechern_ergibt_keine_kante(self, db_session, faecher):
        bio, chemie, nwt = faecher["bio"], faecher["chemie"], faecher["nwt"]
        await _import(db_session, {"E.md": _md(ENERGIE, bio.slug)})
        await _import(db_session, {"E.md": _md(ENERGIE, chemie.slug, abgrenzung=[
            leite_id_ab(bio.fach_code, "E")])})
        bilanz = await _import(db_session, {"Blatt.md": _md(f"Blatt{TOKEN}", nwt.slug,
                                                              verwandt=[ENERGIE])})
        blatt = await _knoten(db_session, f"Blatt{TOKEN}", nwt)
        assert await _kanten(db_session, blatt) == []
        assert any("mehrdeutig" in w and ENERGIE in w for w in bilanz.warnungen), bilanz.warnungen

    async def test_kennung_mit_fremdem_fachkuerzel_gilt_in_jedem_fach(self, db_session, faecher):
        """Ein Fach ohne Bezug: über den Titel nichts — über die Kennung eindeutig."""
        fremd, nwt = faecher["fremd"], faecher["nwt"]
        await _import(db_session, {f"{OSMOSE}.md": _md(OSMOSE, fremd.slug)})
        kennung = leite_id_ab(fremd.fach_code, OSMOSE)

        ueber_titel = await _import(db_session, {"A.md": _md(f"A{TOKEN}", nwt.slug,
                                                                 verwandt=[OSMOSE])})
        assert ueber_titel.offene_ziele[OSMOSE] == 1

        ueber_kennung = await _import(db_session, {"B.md": _md(f"B{TOKEN}", nwt.slug,
                                                                   verwandt=[kennung])})
        b = await _knoten(db_session, f"B{TOKEN}", nwt)
        assert [(t, s) for t, s, _ in await _kanten(db_session, b)] == [(OSMOSE, fremd.id)]
        assert ueber_kennung.ueber_fachgrenzen == {f"{kennung} ({fremd.name})": 1}

    async def test_erneuter_import_schliesst_das_offene_ziel(self, db_session, faecher):
        bio, nwt = faecher["bio"], faecher["nwt"]
        datei = {"Blatt.md": _md(f"Blatt{TOKEN}", nwt.slug, verwandt=[SYNTHESE])}
        erst = await _import(db_session, datei)
        assert erst.offene_ziele[SYNTHESE] == 1
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        zweit = await _import(db_session, datei)
        assert SYNTHESE not in zweit.offene_ziele
        blatt = await _knoten(db_session, f"Blatt{TOKEN}", nwt)
        assert [t for t, _, _ in await _kanten(db_session, blatt)] == [SYNTHESE]


    async def test_rundreise_haelt_die_kante_ueber_die_fachgrenze(self, db_session, faecher):
        """Export → Import: Der Import setzt seine Kanten aus der Datei neu. Schriebe der
        Export ein fremdes Ziel nicht hin, verschwände die Abgrenzung beim Rundgang."""
        from app.context.fachbegriffe_export import exportiere
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        kennung = leite_id_ab(bio.fach_code, SYNTHESE)
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, nwt.slug, abgrenzung=[kennung])})

        dateien, _ = await exportiere(db_session, nwt)
        text = next(d.inhalt.decode() for d in dateien if d.pfad == f"{SYNTHESE}.md")
        assert f"[[{kennung}]]" in text
        bilanz = await _import(db_session, {d.pfad: d.inhalt for d in dateien})
        assert bilanz.unveraendert == 1 and [z.folge for z in bilanz.kollisionen] == ["abgegrenzt"]
        knoten = await _knoten(db_session, SYNTHESE, nwt)
        assert [(t, s, m["art"]) for t, s, m in await _kanten(db_session, knoten)] == [
            (SYNTHESE, bio.id, "abgrenzung")]


class TestDublettenImImport:
    async def test_ohne_abgrenzung_uebergangen_mit_abgrenzung_angelegt(self, db_session, faecher):
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        kennung = leite_id_ab(bio.fach_code, SYNTHESE)

        ohne = await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, nwt.slug)})
        assert await _knoten(db_session, SYNTHESE, nwt) is None
        assert [d.zustand for d in ohne.dateien] == ["uebergangen"]
        assert [(z.folge, z.gegen.fach) for z in ohne.kollisionen] == [("uebergangen", bio.name)]
        assert any(f"[[{kennung}]]" in w for w in ohne.warnungen), ohne.warnungen

        mit = await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, nwt.slug,
                                                                  abgrenzung=[kennung])})
        neu = await _knoten(db_session, SYNTHESE, nwt)
        assert neu is not None and mit.neu == 1
        assert [(z.folge) for z in mit.kollisionen] == ["abgegrenzt"]
        [(ziel, fach, metadata)] = await _kanten(db_session, neu)
        assert (ziel, fach, metadata["art"]) == (SYNTHESE, bio.id, "abgrenzung")

    async def test_symmetrisch(self, db_session, faecher):
        """Wer zuerst da war, entscheidet nicht über Recht — der zweite braucht die Abgrenzung."""
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, nwt.slug)})
        bilanz = await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        assert await _knoten(db_session, SYNTHESE, bio) is None
        assert [z.folge for z in bilanz.kollisionen] == ["uebergangen"]

    async def test_titel_gleich_fremdem_suchbegriff_sperrt(self, db_session, faecher):
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug,
                                                            aliase=[f"Photo{SYNTHESE}"])})
        bilanz = await _import(db_session, {"P.md": _md(f"Photo{SYNTHESE}", nwt.slug)})
        assert [(z.gegen.art, z.folge) for z in bilanz.kollisionen] == [("titel_alias", "uebergangen")]

    async def test_suchbegriff_gleich_suchbegriff_ist_nur_ein_hinweis(self, db_session, faecher):
        bio, nwt = faecher["bio"], faecher["nwt"]
        power = f"Power{TOKEN}"
        await _import(db_session, {"E.md": _md(ENERGIE, bio.slug, aliase=[power])})
        bilanz = await _import(db_session, {"L.md": _md(f"Leistung{TOKEN}", nwt.slug, aliase=[power])})
        assert bilanz.neu == 1
        assert [(z.gegen.art, z.folge) for z in bilanz.kollisionen] == [("alias", "hinweis")]

    async def test_fassungen_im_selben_fach_loesen_nichts_aus(self, db_session, faecher):
        bio = faecher["bio"]
        bilanz = await _import(db_session, {
            f"{SYNTHESE} (Grund).md": _md(SYNTHESE, bio.slug),
            f"{SYNTHESE} (vertieft).md": _md(SYNTHESE, bio.slug),
        })
        assert bilanz.neu == 2 and bilanz.kollisionen == []

    async def test_vorhandene_kollision_blockiert_keine_aktualisierung(self, db_session, faecher):
        """Ein Eintrag aus der Zeit vor 0.16 — er steht in der Bestandsliste, nicht im Weg."""
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        db_session.add(ContextNode(
            category="concept", content_type="begriff", title=SYNTHESE, content="Alt.",
            subject_id=nwt.id, status="active", read_scope="school", write_scope="school",
            metadata_={"seed_id": leite_id_ab(nwt.fach_code, SYNTHESE)},
        ))
        await db_session.flush()
        bilanz = await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, nwt.slug)})
        assert bilanz.aktualisiert == 1 or bilanz.uebersprungen == [SYNTHESE]
        assert [z.folge for z in bilanz.kollisionen] == ["bestand"]

    async def test_neuer_titel_schafft_die_kollision_erst(self, db_session, faecher):
        bio, nwt = faecher["bio"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        kennung = f"{nwt.fach_code.lower()}-blatt"
        await _import(db_session, {"Blatt.md": _md(f"Blatt{TOKEN}", nwt.slug, kennung=kennung)})
        bilanz = await _import(db_session, {"Blatt.md": _md(SYNTHESE, nwt.slug, kennung=kennung)})
        assert [d.zustand for d in bilanz.dateien] == ["uebergangen"]
        assert await _knoten(db_session, f"Blatt{TOKEN}", nwt) is not None


class TestBestandsliste:
    async def test_paare_mit_art_und_abgrenzung(self, db_session, faecher):
        bio, chemie, nwt = faecher["bio"], faecher["chemie"], faecher["nwt"]
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, bio.slug)})
        await _import(db_session, {f"{SYNTHESE}.md": _md(SYNTHESE, nwt.slug, abgrenzung=[
            leite_id_ab(bio.fach_code, SYNTHESE)])})
        for titel, fach in ((ZELLE, bio), (ZELLE, chemie)):   # vor 0.16 entstanden
            db_session.add(ContextNode(category="concept", content_type="begriff", title=titel,
                                       content="x", subject_id=fach.id, status="active",
                                       read_scope="school", write_scope="school"))
        await db_session.flush()
        eigene = {(p.a.titel, p.a.fach, p.b.fach, p.art, p.abgegrenzt) for p in await bestand(db_session)
                  if TOKEN in p.a.titel}
        assert eigene == {
            (SYNTHESE, bio.name, nwt.name, "titel", True),
            (ZELLE, bio.name, chemie.name, "titel", False),
        }


# ── Editor ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def editorbestand(async_engine):
    """Committet — der Testclient arbeitet in eigenen Sitzungen."""
    factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        bio = await _fach(s, "Bio", f"B{TOKEN[:3]}".upper())
        nwt = await _fach(s, "NwT", f"N{TOKEN[:3]}".upper(), bezug=[bio.slug])
        knoten = {}
        for titel, fach, extra in (
            (SYNTHESE, bio, {}),
            (f"Blatt{TOKEN}", nwt, {}),
            (ZELLE, bio, {}), (ZELLE, nwt, {}),             # Altlast von vor 0.16
            (f"Privat{TOKEN}", bio, {"read_scope": "private", "write_scope": "private",
                                     "owner_pseudonym": "jemand-anderes"}),
        ):
            k = ContextNode(category="concept", content_type="begriff", title=titel, content="x",
                            subject_id=fach.id, status="active",
                            **({"read_scope": "school", "write_scope": "school"} | extra))
            s.add(k)
            await s.flush()
            knoten[(titel, fach.id)] = k.id
        await s.commit()
    yield {"bio": bio, "nwt": nwt, "knoten": knoten}
    async with factory() as s:
        await s.execute(sa.delete(ContextNode).where(ContextNode.title.like(f"%{TOKEN}%")))
        await s.execute(sa.delete(Subject).where(Subject.id.in_([bio.id, nwt.id])))
        await s.commit()


def _neu(titel, subject_id, **extra):
    return {"category": "concept", "content_type": "begriff", "title": titel,
            "content": "Ein Text.", "subject_id": subject_id, "read_scope": "school",
            "write_scope": "private", **extra}


class TestEditor:
    async def test_anlegen_ohne_abgrenzung_wird_abgelehnt(self, test_client, auth_headers,
                                                          editorbestand):
        nwt, bio = editorbestand["nwt"], editorbestand["bio"]
        antwort = await test_client.post("/context/nodes", json=_neu(SYNTHESE, nwt.id),
                                         headers=auth_headers)
        assert antwort.status_code == 409, antwort.text
        detail = antwort.json()["detail"]
        assert detail["grund"] == "kollision"
        assert [(k["titel"], k["fach"]) for k in detail["kollisionen"]] == [(SYNTHESE, bio.name)]

    async def test_anderer_titel_geht_durch(self, test_client, auth_headers, editorbestand):
        """Gegenprobe: Ohne Namensgleichheit legt der Editor an wie bisher."""
        antwort = await test_client.post(
            "/context/nodes", json=_neu(f"Einzigartig{TOKEN}", editorbestand["nwt"].id),
            headers=auth_headers)
        assert antwort.status_code == 201, antwort.text

    async def test_anlegen_mit_abgrenzung_legt_die_kante_an(self, test_client, auth_headers,
                                                            editorbestand, async_engine):
        nwt, bio = editorbestand["nwt"], editorbestand["bio"]
        ziel = editorbestand["knoten"][(SYNTHESE, bio.id)]
        antwort = await test_client.post(
            "/context/nodes", json=_neu(SYNTHESE, nwt.id, abgrenzung_zu=[str(ziel)]),
            headers=auth_headers)
        assert antwort.status_code == 201, antwort.text
        factory = async_sessionmaker(async_engine, class_=AsyncSession)
        async with factory() as s:
            kanten = (await s.execute(sa.select(ContextEdge.to_node_id, ContextEdge.metadata_)
                      .where(ContextEdge.from_node_id == uuid.UUID(antwort.json()["id"])))).all()
        assert [(z, m["art"]) for z, m in kanten] == [(ziel, "abgrenzung")]

    async def test_umbenennen_in_kollision_braucht_abgrenzung(self, test_client, auth_headers,
                                                              editorbestand):
        nwt, bio = editorbestand["nwt"], editorbestand["bio"]
        blatt = editorbestand["knoten"][(f"Blatt{TOKEN}", nwt.id)]
        antwort = await test_client.patch(f"/context/nodes/{blatt}", json={"title": SYNTHESE},
                                          headers=auth_headers)
        assert antwort.status_code == 409
        ziel = editorbestand["knoten"][(SYNTHESE, bio.id)]
        antwort = await test_client.patch(f"/context/nodes/{blatt}", headers=auth_headers,
                                          json={"title": SYNTHESE, "abgrenzung_zu": [str(ziel)]})
        assert antwort.status_code == 200, antwort.text

    async def test_alte_kollision_blockiert_keine_bearbeitung(self, test_client, auth_headers,
                                                              editorbestand):
        nwt = editorbestand["nwt"]
        alt = editorbestand["knoten"][(ZELLE, nwt.id)]
        antwort = await test_client.patch(f"/context/nodes/{alt}", headers=auth_headers,
                                          json={"content": "Überarbeitet.", "aliase": ["Zellchen"]})
        assert antwort.status_code == 200, antwort.text

    async def test_abgrenzung_nur_zu_lesbaren_fachbegriffen(self, test_client, auth_headers,
                                                            editorbestand):
        bio = editorbestand["bio"]
        privat = editorbestand["knoten"][(f"Privat{TOKEN}", bio.id)]
        antwort = await test_client.post(
            "/context/nodes",
            json=_neu(f"Noch{TOKEN}", editorbestand["nwt"].id, abgrenzung_zu=[str(privat)]),
            headers=auth_headers)
        assert antwort.status_code == 422

    async def test_privat_oder_archiviert_zaehlt_nicht(self, db_session):
        """Geprüft wird gegen **aktive, allgemein lesbare** Fachbegriffe: Ein privater
        Entwurf ist kein Bestand des Fachs — und sein Titel gehört in keine fremde Meldung."""
        fach = await _fach(db_session, "Archiv", f"A{TOKEN[:3]}".upper())
        for titel, extra in ((f"Archiviert{TOKEN}", {"status": "archived", "read_scope": "school"}),
                             (f"Privat{TOKEN}", {"status": "active", "read_scope": "private",
                                                 "owner_pseudonym": "jemand-anderes"}),
                             (f"Offen{TOKEN}", {"status": "active", "read_scope": "school"})):
            db_session.add(ContextNode(category="concept", content_type="begriff", title=titel,
                                       content="x", subject_id=fach.id, write_scope="private",
                                       **extra))
        await db_session.flush()
        for titel in (f"Archiviert{TOKEN}", f"Privat{TOKEN}"):
            assert await kollisionen(db_session, subject_id=None, titel=titel) == [], titel
        assert len(await kollisionen(db_session, subject_id=None, titel=f"Offen{TOKEN}")) == 1
