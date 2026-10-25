"""Auslöser-Beispiele und Vorschlagsfelder am Assistenten (Päckchen C1, Schritt 3).

Über die echte Schnittstelle: Anlegen, Ändern (Abgleich behält Vektoren), Löschen
(Rückfall-Listen der anderen), YAML-Rundreise und das Einbetten — samt Modellwechsel.
Erfordert TEST_DATABASE_URL.
"""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistants import ausloeser
from app.config import settings
from app.context.embedding import EmbeddingStapel
from app.db.models import Assistant, AssistantTriggerExample

pytestmark = pytest.mark.asyncio

PRAEFIX = "AUS "
STAPEL = "app.assistants.ausloeser.generate_embeddings"


@pytest_asyncio.fixture
async def sitzungen(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def aufraeumen(sitzungen):
    yield
    async with sitzungen() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


def _neu(name, **mehr):
    return {"name": PRAEFIX + name, "system_prompt": "P", "audience": "student", **mehr}


async def _anlegen(client, headers, name, **mehr):
    resp = await client.post("/assistants", json=_neu(name, **mehr), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _zeilen(sitzungen, assistant_id):
    async with sitzungen() as db:
        return (await db.execute(
            sa.select(AssistantTriggerExample)
            .where(AssistantTriggerExample.assistant_id == assistant_id)
            .order_by(AssistantTriggerExample.art, AssistantTriggerExample.position)
        )).scalars().all()


async def _setze_vektor(sitzungen, assistant_id, text, modell):
    async with sitzungen() as db:
        await db.execute(
            sa.update(AssistantTriggerExample)
            .where(AssistantTriggerExample.assistant_id == assistant_id,
                   AssistantTriggerExample.text_ == text)
            .values(embedding=[0.1, 0.2, 0.3], embedding_model=modell)
        )
        await db.commit()


class TestAnlegenUndLesen:
    async def test_felder_und_listen_kommen_zurueck(self, test_client, auth_headers):
        rueck = await _anlegen(test_client, auth_headers, "Rückfall", suggest="fallback")
        a = await _anlegen(
            test_client, auth_headers, "Spezifisch",
            suggest="specific",
            suggestion_text="  Eine Rechenhilfe, die dich begleitet.  ",
            fallbacks=[rueck["id"], rueck["id"]],
            trigger_examples=[" Wie viel g CO2 entstehen? ", "", "Wie viel g CO2 entstehen?",
                              "Berechne die Masse"],
            trigger_counterexamples=["Was ist ein Mol?"],
        )
        assert a["suggest"] == "specific"
        assert a["suggestion_text"] == "Eine Rechenhilfe, die dich begleitet."
        assert a["fallbacks"] == [rueck["id"]]
        assert a["trigger_examples"] == ["Wie viel g CO2 entstehen?", "Berechne die Masse"]
        assert a["trigger_counterexamples"] == ["Was ist ein Mol?"]

        einzel = (await test_client.get(f"/assistants/{a['id']}", headers=auth_headers)).json()
        assert einzel["trigger_examples"] == a["trigger_examples"]
        assert einzel["trigger_counterexamples"] == a["trigger_counterexamples"]

    async def test_vorgabe_never_ohne_listen(self, test_client, auth_headers):
        a = await _anlegen(test_client, auth_headers, "Schlicht")
        assert a["suggest"] == "never"
        assert a["fallbacks"] == []
        assert a["trigger_examples"] == []

    async def test_uebersicht_meldet_listen_als_nicht_geladen(self, test_client, auth_headers):
        await _anlegen(test_client, auth_headers, "Liste", trigger_examples=["x"])
        items = (await test_client.get("/assistants/mine", headers=auth_headers)).json()["items"]
        eintrag = next(i for i in items if i["name"] == PRAEFIX + "Liste")
        assert eintrag["trigger_examples"] is None


class TestAendern:
    async def test_abgleich_behaelt_vektor_unveraenderter_texte(
        self, test_client, auth_headers, sitzungen
    ):
        a = await _anlegen(test_client, auth_headers, "Abgleich",
                           trigger_examples=["eins", "zwei", "drei"])
        await _setze_vektor(sitzungen, a["id"], "zwei", settings.embedding_model)
        vorher = {z.text_: z.id for z in await _zeilen(sitzungen, a["id"])}

        resp = await test_client.patch(
            f"/assistants/{a['id']}",
            json={"trigger_examples": ["zwei", "vier", "eins"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["trigger_examples"] == ["zwei", "vier", "eins"]

        zeilen = {z.text_: z for z in await _zeilen(sitzungen, a["id"])}
        assert set(zeilen) == {"zwei", "vier", "eins"}
        assert zeilen["zwei"].id == vorher["zwei"]
        assert zeilen["zwei"].embedding is not None
        assert zeilen["vier"].embedding is None
        assert [zeilen[t].position for t in ("zwei", "vier", "eins")] == [0, 1, 2]

    async def test_ohne_listenfeld_bleibt_alles(self, test_client, auth_headers):
        a = await _anlegen(test_client, auth_headers, "Bleibt",
                           trigger_examples=["a"], trigger_counterexamples=["b"])
        resp = await test_client.patch(
            f"/assistants/{a['id']}", json={"description": "neu"}, headers=auth_headers
        )
        assert resp.json()["trigger_examples"] == ["a"]
        assert resp.json()["trigger_counterexamples"] == ["b"]

    async def test_leere_liste_leert(self, test_client, auth_headers):
        a = await _anlegen(test_client, auth_headers, "Leeren", trigger_examples=["a"])
        resp = await test_client.patch(
            f"/assistants/{a['id']}", json={"trigger_examples": []}, headers=auth_headers
        )
        assert resp.json()["trigger_examples"] == []

    async def test_suggest_null_aendert_nichts(self, test_client, auth_headers):
        a = await _anlegen(test_client, auth_headers, "Null", suggest="fallback")
        resp = await test_client.patch(
            f"/assistants/{a['id']}", json={"suggest": None}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["suggest"] == "fallback"


class TestPruefungen:
    @pytest.mark.parametrize("feld,wert", [
        ("suggest", "immer"),
        ("trigger_examples", [f"t{i}" for i in range(ausloeser.MAX_EINTRAEGE + 1)]),
        ("trigger_counterexamples", ["x" * (ausloeser.MAX_ZEICHEN + 1)]),
        ("fallbacks", [987654321]),
        ("suggestion_text", "x" * 301),
    ])
    async def test_abgelehnt(self, test_client, auth_headers, feld, wert):
        resp = await test_client.post(
            "/assistants", json=_neu("Falsch", **{feld: wert}), headers=auth_headers
        )
        assert resp.status_code == 422, resp.text

    async def test_nicht_eigener_rueckfall(self, test_client, auth_headers):
        a = await _anlegen(test_client, auth_headers, "Selbst")
        resp = await test_client.patch(
            f"/assistants/{a['id']}", json={"fallbacks": [a["id"]]}, headers=auth_headers
        )
        assert resp.status_code == 422

    async def test_hoechstens_drei_rueckfaelle(self, test_client, auth_headers):
        ids = [(await _anlegen(test_client, auth_headers, f"R{i}"))["id"] for i in range(4)]
        resp = await test_client.post(
            "/assistants", json=_neu("Viele", fallbacks=ids), headers=auth_headers
        )
        assert resp.status_code == 422


class TestLoeschen:
    async def test_geloeschter_verschwindet_aus_rueckfaellen_und_beispielen(
        self, test_client, auth_headers, sitzungen
    ):
        rueck = await _anlegen(test_client, auth_headers, "Weg", trigger_examples=["a"])
        bleibt = await _anlegen(test_client, auth_headers, "Bleibt2", fallbacks=[rueck["id"]])

        resp = await test_client.delete(f"/assistants/{rueck['id']}", headers=auth_headers)
        assert resp.status_code == 204

        nachher = (await test_client.get(f"/assistants/{bleibt['id']}", headers=auth_headers))
        assert nachher.json()["fallbacks"] == []
        assert await _zeilen(sitzungen, rueck["id"]) == []


class TestYamlRundreise:
    async def test_export_import_traegt_alles(self, test_client, auth_headers):
        rueck = await _anlegen(test_client, auth_headers, "NW-Aufgaben", suggest="fallback")
        a = await _anlegen(
            test_client, auth_headers, "Stöchio",
            suggest="specific", suggestion_text="Rechenhilfe.",
            fallbacks=[rueck["id"]],
            trigger_examples=["eins", "zwei"], trigger_counterexamples=["drei"],
        )
        export = await test_client.get(f"/assistants/{a['id']}/export", headers=auth_headers)
        assert export.status_code == 200
        assert f"- {PRAEFIX}NW-Aufgaben" in export.text  # Name, nicht ID

        resp = await test_client.post(
            "/assistants/import",
            files={"file": ("a.yaml", export.content, "application/x-yaml")},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        neu = resp.json()
        assert neu["suggest"] == "specific"
        assert neu["suggestion_text"] == "Rechenhilfe."
        assert neu["fallbacks"] == [rueck["id"]]
        assert neu["trigger_examples"] == ["eins", "zwei"]
        assert neu["trigger_counterexamples"] == ["drei"]
        assert neu["hinweise"] == []

    async def test_unbekannter_rueckfall_wird_genannt(self, test_client, auth_headers):
        yaml_text = (
            "metadata:\n"
            f"  name: {PRAEFIX}Fremd\n"
            "  audience: student\n"
            "  fallbacks: [Gibt es hier nicht]\n"
            "config:\n"
            "  system_prompt: P\n"
        )
        resp = await test_client.post(
            "/assistants/import",
            files={"file": ("a.yaml", yaml_text.encode(), "application/x-yaml")},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["fallbacks"] == []
        assert any("Gibt es hier nicht" in h for h in resp.json()["hinweise"])

    async def test_alter_export_ohne_felder(self, test_client, auth_headers):
        yaml_text = (
            "metadata:\n"
            f"  name: {PRAEFIX}Alt\n"
            "  audience: student\n"
            "config:\n"
            "  system_prompt: P\n"
        )
        resp = await test_client.post(
            "/assistants/import",
            files={"file": ("a.yaml", yaml_text.encode(), "application/x-yaml")},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["suggest"] == "never"
        assert resp.json()["trigger_examples"] == []


def _attrappe(dim=3):
    async def _f(texte):
        return EmbeddingStapel(vektoren=[[0.5] * dim for _ in texte], tokens=len(texte))
    return AsyncMock(side_effect=_f)


class TestEinbetten:
    async def test_offene_und_fremdes_modell_werden_eingebettet(
        self, test_client, auth_headers, sitzungen, monkeypatch
    ):
        a = await _anlegen(test_client, auth_headers, "Einbetten",
                           trigger_examples=["neu", "aktuell", "veraltet"])
        await _setze_vektor(sitzungen, a["id"], "aktuell", settings.embedding_model)
        await _setze_vektor(sitzungen, a["id"], "veraltet", "altes-modell")

        monkeypatch.setattr(settings, "embeddings_enabled", True)
        mock = _attrappe()
        with patch(STAPEL, new=mock):
            async with sitzungen() as db:
                stand = await ausloeser.einbetten(db, [a["id"]])

        assert (stand.gefunden, stand.ok, stand.fehler) == (2, 2, 0)
        assert sorted(mock.await_args.args[0]) == ["neu", "veraltet"]
        for z in await _zeilen(sitzungen, a["id"]):
            assert z.embedding_model == settings.embedding_model
            assert z.embedding is not None

    async def test_fehler_laesst_zeilen_offen(
        self, test_client, auth_headers, sitzungen, monkeypatch
    ):
        a = await _anlegen(test_client, auth_headers, "Fehler", trigger_examples=["x"])
        monkeypatch.setattr(settings, "embeddings_enabled", True)
        with patch(STAPEL, new=AsyncMock(side_effect=RuntimeError("Proxy weg"))):
            async with sitzungen() as db:
                stand = await ausloeser.einbetten(db, [a["id"]])
        assert (stand.ok, stand.fehler) == (0, 1)
        assert (await _zeilen(sitzungen, a["id"]))[0].embedding is None

    async def test_ausgeschaltet_ruft_nichts(self, test_client, auth_headers, sitzungen):
        a = await _anlegen(test_client, auth_headers, "Aus", trigger_examples=["x"])
        mock = _attrappe()
        with patch(STAPEL, new=mock):
            async with sitzungen() as db:
                stand = await ausloeser.einbetten(db, [a["id"]])
        assert stand.gefunden == 0
        mock.assert_not_awaited()

    async def test_speichern_bettet_im_hintergrund_ein(
        self, test_client, auth_headers, sitzungen, monkeypatch
    ):
        monkeypatch.setattr(settings, "embeddings_enabled", True)
        with patch(STAPEL, new=_attrappe()):
            a = await _anlegen(test_client, auth_headers, "Hintergrund",
                               trigger_examples=["x", "y"])
        zeilen = await _zeilen(sitzungen, a["id"])
        assert [z.embedding_model for z in zeilen] == [settings.embedding_model] * 2
