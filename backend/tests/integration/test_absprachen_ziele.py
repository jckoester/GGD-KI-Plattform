"""Absprachen (0.63, AY Teil 2, Schritt 1): Ziele gegen die Datenbank. Erfordert TEST_DATABASE_URL."""
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.context.absprachen import normalisieren, ziele_pruefen
from app.db.models import ContextNode

pytestmark = pytest.mark.asyncio


async def _fach(db, slug, code):
    return (await db.execute(sa.text(
        "INSERT INTO subjects (slug, name, fach_code) VALUES (:s, :n, :c) "
        "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code RETURNING id"),
        {"s": slug, "n": slug.title(), "c": code})).scalar_one()


def _knoten(typ, titel, subject_id, status="active"):
    return ContextNode(id=uuid.uuid4(), category="knowledge", content_type=typ, title=titel, status=status,
                       owner_pseudonym="system", read_scope="school", write_scope="school",
                       subject_id=subject_id, metadata_={})


@pytest_asyncio.fixture
async def welt(db_session):
    ph = await _fach(db_session, "physik-abspr", "PHAB")
    ch = await _fach(db_session, "chemie-abspr", "CHAB")
    dichte = _knoten("kapitel", "Dichte", ph)
    entwurf = _knoten("kapitel", "Auftrieb", ph, status="draft")
    alt = _knoten("kapitel", "Altes Kapitel", ph, status="archived")
    stoffe = _knoten("kapitel", "Stoffe", ch)
    cur = _knoten("curriculum", "Physik Kl. 8", ph)
    db_session.add_all([dichte, entwurf, alt, stoffe, cur])
    await db_session.flush()
    return {"dichte": dichte, "entwurf": entwurf, "alt": alt, "stoffe": stoffe, "cur": cur}


async def test_kapitel_des_fachs_titel_aus_der_datenbank(db_session, welt):
    a = normalisieren([{"fach_code": "PHAB", "kapitel_id": str(welt["dichte"].id), "kapitel_titel": "veraltet",
                        "art": "vorher", "text": ""},
                       {"fach_code": "PHAB", "kapitel_id": str(welt["entwurf"].id), "art": "gleichzeitig"},
                       {"fach_code": "PHAB", "art": "abgestimmt", "text": "Begriffe einheitlich"}], "M")
    geprueft = await ziele_pruefen(db_session, a)
    assert [x["kapitel_titel"] for x in geprueft] == ["Dichte", "Auftrieb", None]
    assert a[0]["kapitel_titel"] == "veraltet"   # Kopie, Eingabe unverändert


@pytest.mark.parametrize("ziel", ["stoffe", "alt", "cur"])
async def test_falsches_ziel(db_session, welt, ziel):
    a = normalisieren([{"fach_code": "PHAB", "kapitel_id": str(welt[ziel].id), "art": "vorher"}])
    with pytest.raises(ValueError, match="gehört nicht zu einem Curriculum von „PHAB“"):
        await ziele_pruefen(db_session, a)


async def test_unbekanntes_fach_und_kapitel(db_session, welt):
    with pytest.raises(ValueError, match="„XYZ“ gibt es hier nicht"):
        await ziele_pruefen(db_session, normalisieren([{"fach_code": "XYZ", "art": "abgestimmt", "text": "t"}]))
    with pytest.raises(ValueError, match="gehört nicht"):
        await ziele_pruefen(db_session, normalisieren([{"fach_code": "PHAB", "kapitel_id": str(uuid.uuid4()),
                                                        "art": "nachher"}]))


async def test_pruefe_absprachen_beim_speichern(db_session, welt):
    from app.context.absprachen import pruefe_absprachen

    ch = welt["stoffe"].subject_id
    meta = {"std": 4, "absprachen": [{"fach_code": "phab", "kapitel_id": str(welt["dichte"].id), "art": "vorher"}]}
    aus = await pruefe_absprachen(db_session, "kapitel", meta, ch)
    assert aus["std"] == 4 and aus["absprachen"][0]["fach_code"] == "PHAB"
    assert aus["absprachen"][0]["kapitel_titel"] == "Dichte" and aus["absprachen"][0]["id"]
    # Leere Liste fällt weg, andere Typen und Kapitel ohne Absprachen bleiben unberührt
    assert await pruefe_absprachen(db_session, "kapitel", {"std": 4, "absprachen": []}, ch) == {"std": 4}
    assert await pruefe_absprachen(db_session, "lernsequenz", {"absprachen": "x"}, ch) == {"absprachen": "x"}
    assert await pruefe_absprachen(db_session, "kapitel", {"std": 1}, ch) == {"std": 1}
    # Das eigene Fach kommt aus `subject_id`
    with pytest.raises(ValueError, match="nicht dem eigenen"):
        await pruefe_absprachen(db_session, "kapitel", {"absprachen": [
            {"fach_code": "CHAB", "art": "abgestimmt", "text": "t"}]}, ch)
