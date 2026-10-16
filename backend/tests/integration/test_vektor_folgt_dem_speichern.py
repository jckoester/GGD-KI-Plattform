"""Der Vektor folgt dem Speichern — auf den Wegen über `/context/nodes` (0.17).

Bis 0.17 bettete `PATCH /context/nodes/{id}` nach einer Änderung neu ein, ließ aber den alten
Vektor stehen, wenn das scheiterte (der Backfill nimmt nur Knoten ohne Vektor und holte ihn
nie nach) oder wenn der Knoten danach keine Substanz mehr hatte. Umbenennen über
`/title` und `/verwalten` zog den Vektor gar nicht nach. Jetzt wird er verworfen, sobald
sich der Eingabetext ändert — und nur dann.

Die Tests laufen mit abgeschalteten Embeddings: `enqueue_embedding_job` kehrt früh zurück,
ein verworfener Vektor bleibt also sichtbar `None`.
"""
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import ContextNode
from tests.integration.conftest import TEACHER1_PSEUDO

PRAEFIX = "Vektor-folgt "
VEKTOR = [0.5] + [0.0] * (settings.embedding_dimensions - 1)


def _sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def knoten(async_engine, db_url, run_migrations):
    """Legt eigene Knoten mit Vektor an und räumt sie danach weg."""
    angelegt: list[UUID] = []

    async def anlegen(art="arbeitsblatt", category="artifact", **kw) -> str:
        async with _sitzungen(async_engine)() as db:
            n = ContextNode(category=category, content_type=art, title=PRAEFIX + kw.pop("title", "AB"),
                            content=kw.pop("content", "Text über Mesomerie im Benzolring."),
                            status="active", read_scope="private", write_scope="private",
                            owner_pseudonym=TEACHER1_PSEUDO, metadata_=kw.pop("metadata_", {}),
                            embedding=VEKTOR, **kw)
            db.add(n)
            await db.commit()
            angelegt.append(n.id)
            return str(n.id)

    yield anlegen
    async with _sitzungen(async_engine)() as db:
        for nid in angelegt:
            n = await db.get(ContextNode, nid)
            if n is not None:
                await db.delete(n)
        await db.commit()


async def _hat_vektor(async_engine, nid) -> bool:
    async with _sitzungen(async_engine)() as db:
        return (await db.get(ContextNode, UUID(nid))).embedding is not None


@pytest.mark.asyncio
async def test_neuer_inhalt_verwirft_den_vektor(test_client, auth_headers, knoten, async_engine):
    nid = await knoten()
    with patch("app.context.router.enqueue_embedding_job", AsyncMock()) as einbetten:
        resp = await test_client.patch(f"/context/nodes/{nid}", headers=auth_headers,
                                       json={"content": "Ganz anderer Text über Alkane."})
        assert resp.status_code == 200, resp.text
    assert not await _hat_vektor(async_engine, nid)
    einbetten.assert_awaited_once()


@pytest.mark.asyncio
async def test_scope_laesst_den_vektor(test_client, auth_headers, knoten, async_engine):
    nid = await knoten()
    with patch("app.context.router.enqueue_embedding_job", AsyncMock()) as einbetten:
        resp = await test_client.patch(f"/context/nodes/{nid}", headers=auth_headers,
                                       json={"valid_until": "2027-07-31"})
        assert resp.status_code == 200, resp.text
    assert await _hat_vektor(async_engine, nid)
    einbetten.assert_not_awaited()


@pytest.mark.asyncio
async def test_gleicher_text_laesst_den_vektor(test_client, auth_headers, knoten, async_engine):
    """Metadaten, die nicht im Eingabetext stehen: Der Vektor stimmt noch und bleibt —
    scheitert das Neueinbetten, ist er nicht verloren."""
    nid = await knoten()
    resp = await test_client.patch(f"/context/nodes/{nid}", headers=auth_headers,
                                   json={"metadata": {"notiz": "nur für mich"}})
    assert resp.status_code == 200, resp.text
    assert await _hat_vektor(async_engine, nid)


@pytest.mark.asyncio
async def test_ohne_substanz_kein_alter_vektor(test_client, auth_headers, knoten, async_engine):
    """Eine Stunde verliert ihre Kompetenzen: Danach trüge sie nur den Titel — kein Vektor
    mehr statt des alten. `enqueue_embedding_job` kehrt hier früh zurück."""
    nid = await knoten(art="unterrichtsstunde", content=None,
                       metadata_={"phasen": [], "refs": [{"node_id": "00000000-0000-0000-0000-000000000001",
                                                          "typ": "ik", "titel": "3.3.1(1) Mesomerie"}]})
    resp = await test_client.patch(f"/context/nodes/{nid}", headers=auth_headers,
                                   json={"metadata": {"phasen": [], "refs": []}})
    assert resp.status_code == 200, resp.text
    assert not await _hat_vektor(async_engine, nid)


@pytest.mark.asyncio
async def test_aliase_der_methode_verwerfen_den_vektor(test_client, auth_headers, knoten, async_engine):
    """Bei `methode` stehen die Aliase im Eingabetext."""
    nid = await knoten(art="methode", category="knowledge", title="Placemat",
                       content="Jede:r schreibt in ein Feld, dann wird die Mitte gefüllt.")
    resp = await test_client.patch(f"/context/nodes/{nid}", headers=auth_headers,
                                   json={"aliase": ["Platzdeckchen"]})
    assert resp.status_code == 200, resp.text
    assert not await _hat_vektor(async_engine, nid)


@pytest.mark.asyncio
async def test_titel_endpunkt_verwirft_den_vektor(test_client, auth_headers, knoten, async_engine):
    nid = await knoten()
    with patch("app.context.router.enqueue_embedding_job", AsyncMock()) as einbetten:
        resp = await test_client.patch(f"/context/nodes/{nid}/title", headers=auth_headers,
                                       json={"title": PRAEFIX + "Ganz neuer Titel"})
        assert resp.status_code == 200, resp.text
    assert not await _hat_vektor(async_engine, nid)
    einbetten.assert_awaited_once()


@pytest.mark.asyncio
async def test_verwalten_umbenennen_verwirft_den_vektor(test_client, auth_headers, knoten, async_engine):
    nid = await knoten()
    with patch("app.context.router.enqueue_embedding_job", AsyncMock()) as einbetten:
        # Nur das Ablaufdatum: kein Modellaufruf, Vektor bleibt.
        resp = await test_client.patch(f"/context/nodes/{nid}/verwalten", headers=auth_headers,
                                       json={"valid_until": "2027-07-31"})
        assert resp.status_code == 200, resp.text
        assert await _hat_vektor(async_engine, nid)
        einbetten.assert_not_awaited()

        resp = await test_client.patch(f"/context/nodes/{nid}/verwalten", headers=auth_headers,
                                       json={"title": PRAEFIX + "Umbenannt"})
        assert resp.status_code == 200, resp.text
    assert not await _hat_vektor(async_engine, nid)
    einbetten.assert_awaited_once()
