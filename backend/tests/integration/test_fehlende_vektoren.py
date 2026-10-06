"""Messskripte prüfen zuerst, ob Vektoren fehlen (0.14, Schritt 1).

Am 06.10.2026 zeigte `vorab_schwelle.py` eine scheinbar zerbrochene Schwelle: Auf Dev
hatten seit einem Neuimport 100 von 107 Begriffen keinen Vektor, und das Skript maß den
Zustand der Vektoren, nicht die Suche. „Fehlend" heißt dabei dasselbe wie für den
Backfill: leer **und** einbettbar — ein Knoten, der nur seinen Titel trüge, bekommt
absichtlich keinen Vektor und darf nicht als Lücke zählen, sonst brächen die Skripte bei
jedem Lauf ab.

Die Testdatenbank enthält Knoten anderer Module ohne Vektor; gezählt wird deshalb der
**Zuwachs** durch die hier angelegten Knoten.
"""
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app.context import embedding as embedding_modul
from app.context.embedding import fehlende_vektoren, vektor_luecken_meldung, vor_einer_messung
from app.context.metadata import STUB_MARKIERUNG
from app.db.models import ContextNode


def _knoten(titel, content_type, category, **felder):
    return ContextNode(
        category=category, content_type=content_type, title=titel,
        read_scope="school", write_scope="school", status=felder.pop("status", "active"),
        **felder,
    )


async def _breite(db) -> int:
    return (await db.execute(sa.text(
        "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'context_nodes'::regclass "
        "AND attname = 'embedding'"
    ))).scalar_one()


@pytest.mark.asyncio
async def test_gezaehlt_wird_nur_was_der_backfill_einbetten_wuerde(db_session):
    vorher = await fehlende_vektoren(db_session)
    breite = await _breite(db_session)
    db_session.add_all([
        # fehlt: Inhalt, kein Vektor
        _knoten("Lückenbegriff", "begriff", "concept", content="Eine Definition."),
        # fehlt nicht: hat einen Vektor
        _knoten("Fertigbegriff", "begriff", "concept", content="Eine Definition.",
                embedding=[0.1] * breite),
        # fehlt nicht: archiviert
        _knoten("Altbegriff", "begriff", "concept", content="Eine Definition.",
                status="archived"),
        # fehlt nicht: Stub aus dem Verknüpfen-Dialog — bekommt absichtlich keinen Vektor
        _knoten("Stubbegriff", "begriff", "concept", content="",
                metadata_={STUB_MARKIERUNG: True}),
        # fehlt nicht: Methode nur mit Titel — wäre eine Titelsuche im Vektorraum
        _knoten("Titelmethode", "methode", "knowledge"),
    ])
    await db_session.flush()

    nachher = await fehlende_vektoren(db_session)
    zuwachs = {t: nachher.get(t, 0) - vorher.get(t, 0) for t in set(nachher) | set(vorher)}
    assert {t: n for t, n in zuwachs.items() if n} == {"begriff": 1}


@pytest.mark.asyncio
async def test_typen_grenzen_ein(db_session):
    vorher = await fehlende_vektoren(db_session, ["methode"])
    db_session.add(_knoten("Lückenbegriff2", "begriff", "concept", content="Text."))
    await db_session.flush()
    assert await fehlende_vektoren(db_session, ["methode"]) == vorher
    # Ein Typ ohne Embedding zählt nie
    assert await fehlende_vektoren(db_session, ["gibt_es_nicht"]) == {}


def test_meldung():
    assert vektor_luecken_meldung({}) is None
    meldung = vektor_luecken_meldung({"begriff": 100, "stoffsteckbrief": 12})
    assert "112 Knoten ohne Vektor" in meldung
    assert "begriff 100" in meldung and "embedding_backfill.py" in meldung


@asynccontextmanager
async def _attrappe():
    yield None


@pytest.mark.asyncio
@pytest.mark.parametrize("fehlend, trotzdem, bricht_ab", [
    ({}, False, False),
    ({"begriff": 3}, False, True),
    ({"begriff": 3}, True, False),
])
async def test_vor_einer_messung(fehlend, trotzdem, bricht_ab, capsys):
    async def _fehlend(db, typen=None):
        return fehlend

    with patch.object(embedding_modul, "fehlende_vektoren", _fehlend), \
            patch("app.db.session.AsyncSessionLocal", _attrappe):
        if bricht_ab:
            with pytest.raises(SystemExit) as exc:
                await vor_einer_messung(trotzdem=trotzdem)
            assert exc.value.code == 2
        else:
            await vor_einer_messung(trotzdem=trotzdem)
    if fehlend:
        assert "3 Knoten ohne Vektor" in capsys.readouterr().err
