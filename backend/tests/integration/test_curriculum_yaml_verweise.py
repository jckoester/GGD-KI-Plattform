"""Verweise mit Kennung beim YAML-Import (0.56, Päckchen BA Schritt 1, F5): nur auf Bausteine,
die die Person lesen darf. Erfordert TEST_DATABASE_URL."""
import uuid

import pytest

from app.auth.jwt import JwtPayload
from app.context.curriculum_yaml import verweise_pruefen, zu_entwurf
from app.db.models import ContextNode

pytestmark = pytest.mark.asyncio

ICH = JwtPayload(sub="ba-ich", roles=["teacher"], grade=None, jti="j", iat=0, exp=9999999999)


def _knoten(db, **abw):
    k = ContextNode(id=uuid.uuid4(), category="knowledge", content_type="concept", title="T", status="active",
                    owner_pseudonym="ba-fremd", read_scope="school", write_scope="school", metadata_={})
    for name, wert in abw.items():
        setattr(k, name, wert)
    db.add(k)
    return k


def _entwurf(hinweise, material=""):
    return zu_entwurf({
        "schule": "S", "fach_code": "CH", "schulart": "G", "jahrgangsstufe": "9", "bp_version": "2016",
        "kapitel": [{"titel": "K", "reihenfolge": 1, "lernsequenzen": [
            {"bp_titel": "L", "eintraege": [{"hinweise": hinweise, "material": material}]}]}],
    }).entwurf


async def test_nur_lesbare_bausteine_bleiben_verlinkt(db_session):
    schule = _knoten(db_session)
    eigen_privat = _knoten(db_session, owner_pseudonym=ICH.sub, read_scope="private", write_scope="private")
    fremd_privat = _knoten(db_session, read_scope="private", write_scope="private")
    geloescht = _knoten(db_session, status="deleted")
    await db_session.flush()
    nirgends = uuid.uuid4()

    entwurf = _entwurf(
        f"@[A](lp:{schule.id}) @[B](node:{eigen_privat.id}) @[C](lb:{fremd_privat.id}) #[D](ik:{nirgends})",
        material=f"@[E](node:{geloescht.id}) @[F](node:{fremd_privat.id}) @[G](lp:BNE)")
    warnungen = await verweise_pruefen(db_session, entwurf, ICH)

    e = entwurf.kapitel[0].lernsequenzen[0].eintraege[0]
    assert e.hinweise == f"@[A](lp:{schule.id}) @[B](node:{eigen_privat.id}) C D"
    assert e.material == "E F @[G](lp:BNE)"  # Codes löst der Import auf, nicht diese Prüfung
    assert len(warnungen) == 4
    assert all("nicht lesen darfst" in w for w in warnungen)
    assert warnungen[0].startswith("Kapitel 1, Lernsequenz 1, Eintrag 1, hinweise:")


async def test_ohne_verweise_keine_abfrage(db_session):
    entwurf = _entwurf("nur Text @[BNE](lp:BNE)")
    assert await verweise_pruefen(db_session, entwurf, ICH) == []
