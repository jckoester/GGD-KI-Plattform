"""Unit-Tests für POST /images/{id}/variieren (Mehrmodell-Plan, Schritt 9).

„Variieren" wiederholt denselben Prompt mit derselben Bildart — bewusst ohne Chat-Modell.
Geprüft wird vor allem, dass der zweite Versuch **keine Abkürzung** an den Prüfungen des
ersten vorbei ist: Eigentümerschaft, Team-Freigabe und Blockliste gelten erneut.

Kein `/api`-Präfix: Der Router wird direkt eingebunden (CLAUDE.md).
"""

import os
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.chat import image_models, router as router_modul
from app.config import settings
from app.db.session import get_db
from app.litellm.client import ImageGenerationError, ImageGenerationResult
from app.ratelimit import store as ratelimit_store

BILDARTEN = """\
bildarten:
  - id: standard
    label: "Standard (quadratisch)"
    modell: bild-standard
    formate:
      quadratisch: "1024x1024"
    standardformat: quadratisch
  - id: formatwahl
    label: "Mit Formatwahl"
    modell: bild-flux2
    formate:
      quadratisch: "1024x1024"
      quer: "1344x768"
    standardformat: quer
standard_bildart: standard
"""

EIGNER = "pseudo-1"


def _record(**over):
    basis = dict(
        id=uuid4(), pseudonym=EIGNER, conversation_id=uuid4(), message_id=uuid4(),
        model="bild-standard", bildart="standard", size="1024x1024",
        mime_type="image/png", prompt="Ein roter Würfel",
    )
    basis.update(over)
    return SimpleNamespace(**basis)


@pytest.fixture(autouse=True)
def _frischer_ratelimit():
    """Der Zähler ist prozesslokal und überlebt sonst zwischen den Tests."""
    ratelimit_store.reset()
    yield
    ratelimit_store.reset()


@pytest.fixture
def bildarten_datei(tmp_path, monkeypatch):
    pfad = tmp_path / "image_models.yaml"
    pfad.write_text(textwrap.dedent(BILDARTEN), encoding="utf-8")
    monkeypatch.setattr(settings, "image_models_path", str(pfad))
    image_models.invalidate_image_models_cache()
    yield
    image_models.invalidate_image_models_cache()


@pytest.fixture
def umgebung(bildarten_datei):
    """App + Attrappen. Liefert (client, steuerung) — steuerung.* setzt das Verhalten."""
    steuerung = SimpleNamespace(
        record=_record(),
        erlaubte_modelle=None,          # None = unbekannt → nicht filtern
        block_reason=None,
        key="sk-user",
        ergebnis=ImageGenerationResult(image_bytes=b"PNG", cost_usd=0.032),
        fehler=None,
        gespeichert=[],
        rollen=["teacher"],
    )

    app = FastAPI()
    app.include_router(router_modul.router)

    async def fake_user():
        return JwtPayload(
            sub=EIGNER, roles=steuerung.rollen, grade=None, jti="j", iat=1, exp=9999999999
        )

    async def fake_db():
        db = MagicMock()
        # Der einzige select() im Endpunkt holt den Virtual Key.
        ergebnis = MagicMock()
        ergebnis.scalar_one_or_none.return_value = steuerung.key
        db.execute = AsyncMock(return_value=ergebnis)
        db.commit = AsyncMock()
        yield db

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db

    async def fake_save(db, **kw):
        steuerung.gespeichert.append(kw)
        return uuid4()

    instance = MagicMock()
    instance.close = AsyncMock()

    async def generate(*a, **kw):
        if steuerung.fehler:
            raise steuerung.fehler
        return steuerung.ergebnis

    instance.generate_image = AsyncMock(side_effect=generate)
    steuerung.client = instance

    with patch.object(router_modul, "get_image_record",
                      new=AsyncMock(side_effect=lambda db, i: steuerung.record)), \
         patch.object(router_modul, "save_generated_image", new=fake_save), \
         patch.object(router_modul, "LiteLLMClient", return_value=instance), \
         patch.object(router_modul, "_image_prompt_block_reason",
                      side_effect=lambda p: steuerung.block_reason), \
         patch.object(router_modul, "erlaubte_modelle_fuer",
                      new=AsyncMock(side_effect=lambda r, g: steuerung.erlaubte_modelle)):
        yield TestClient(app), steuerung


def _post(client, image_id=None):
    return client.post(f"/images/{image_id or uuid4()}/variieren")


# ── Der gute Fall ───────────────────────────────────────────────────────────────────


def test_variiert_mit_gleichem_prompt_und_gleicher_bildart(umgebung):
    client, st = umgebung

    resp = _post(client)

    assert resp.status_code == 200
    assert resp.json()["bildart"] == "Standard (quadratisch)"
    assert resp.json()["size"] == "1024x1024"
    call = st.client.generate_image.await_args
    assert call.args[0] == "Ein roter Würfel"
    assert call.kwargs["model"] == "bild-standard"
    assert call.kwargs["api_key"] == "sk-user"


def test_neues_bild_haengt_an_derselben_nachricht(umgebung):
    """Sonst stünden die Varianten beim erneuten Laden nicht bei ihrem Original."""
    client, st = umgebung

    _post(client)

    gespeichert = st.gespeichert[-1]
    assert gespeichert["message_id"] == st.record.message_id
    assert gespeichert["conversation_id"] == st.record.conversation_id
    assert gespeichert["bildart"] == "standard"
    assert gespeichert["prompt"] == "Ein roter Würfel"


def test_groesse_des_originals_gewinnt(umgebung):
    """Auch wenn sie nicht das Standardformat der Bildart ist."""
    client, st = umgebung
    st.record = _record(bildart="formatwahl", model="bild-flux2", size="1024x1024")

    resp = _post(client)

    assert resp.json()["size"] == "1024x1024"  # nicht "1344x768" (Standardformat)
    assert st.client.generate_image.await_args.kwargs["size"] == "1024x1024"


def test_unbekannte_groesse_faellt_auf_das_standardformat(umgebung):
    """Die Bildart wurde umkonfiguriert — nie eine unbepreiste Größe schicken."""
    client, st = umgebung
    st.record = _record(size="4096x4096")

    assert _post(client).json()["size"] == "1024x1024"


# ── Der zweite Versuch ist keine Abkürzung ──────────────────────────────────────────


def test_fremdes_bild_wird_abgelehnt(umgebung):
    client, st = umgebung
    st.record = _record(pseudonym="jemand-anderes")

    assert _post(client).status_code == 403


def test_gesperrtes_modell_wird_abgelehnt(umgebung):
    """Ein altes Bild darf kein Schlupfloch zu einem inzwischen gesperrten Modell sein."""
    client, st = umgebung
    st.erlaubte_modelle = {"chat-standard"}

    resp = _post(client)

    assert resp.status_code == 403
    assert "nicht freigeschaltet" in resp.json()["detail"]
    st.client.generate_image.assert_not_awaited()


def test_unbekannte_freigabe_filtert_nicht(umgebung):
    """None heißt „Proxy nicht erreichbar" — der Proxy entscheidet dann selbst."""
    client, st = umgebung
    st.erlaubte_modelle = None

    assert _post(client).status_code == 200


def test_blockliste_gilt_erneut(umgebung):
    """Sie kann sich seit dem ersten Bild geändert haben."""
    client, st = umgebung
    st.block_reason = "Nicht erlaubtes Motiv."

    resp = _post(client)

    assert resp.status_code == 422
    st.client.generate_image.assert_not_awaited()


# ── Was nicht geht, sagt warum ──────────────────────────────────────────────────────


def test_bild_ohne_prompt(umgebung):
    client, st = umgebung
    st.record = _record(prompt=None)

    resp = _post(client)

    assert resp.status_code == 409
    assert "kein Prompt" in resp.json()["detail"]


def test_entfallene_bildart(umgebung):
    """Konfiguration geändert — dann lieber ein klarer Satz als ein stiller Ersatz."""
    client, st = umgebung
    st.record = _record(bildart="gibt-es-nicht-mehr")

    resp = _post(client)

    assert resp.status_code == 409
    assert "gibt es nicht mehr" in resp.json()["detail"]


def test_altes_bild_ohne_bildart(umgebung):
    client, st = umgebung
    st.record = _record(bildart=None)

    assert _post(client).status_code == 409


def test_ablehnung_des_proxys_wird_uebersetzt(umgebung):
    client, st = umgebung
    st.fehler = ImageGenerationError("nope", status_code=429)

    resp = _post(client)

    assert resp.status_code == 502
    assert "Budget" in resp.json()["detail"]
    st.client.close.assert_awaited_once()


def test_fehlendes_bild_ist_404(umgebung):
    client, st = umgebung
    st.record = None

    assert _post(client).status_code == 404


# ── Drosselung ──────────────────────────────────────────────────────────────────────


def test_variieren_ist_gedrosselt_wie_der_chat(umgebung, monkeypatch):
    """Sonst wäre der Knopf ein Schlupfloch.

    Ein Bild im Chat anzufordern kostet einen gedrosselten Request; dasselbe Bild per Klick
    zu wiederholen dürfte nicht billiger zu haben sein — die einzige verbleibende Bremse
    wäre das EUR-Budget, und das merkt man erst, wenn es leer ist.
    """
    from app.ratelimit import config

    client, st = umgebung
    monkeypatch.setattr(config, "resolve", lambda bucket, roles: (2, 60.0))

    assert _post(client).status_code == 200
    assert _post(client).status_code == 200
    dritter = _post(client)

    assert dritter.status_code == 429
    assert dritter.headers.get("Retry-After")
    # Der abgewiesene Versuch hat kein Bild erzeugt.
    assert st.client.generate_image.await_count == 2


def test_drosselung_nutzt_den_chat_bucket(umgebung, monkeypatch):
    """Damit Rollen-Overrides aus rate_limits.yaml greifen (Lehrkräfte großzügiger)."""
    from app.ratelimit import config

    client, _ = umgebung
    gesehen = []
    original = config.resolve
    monkeypatch.setattr(
        config, "resolve",
        lambda bucket, roles: (gesehen.append(bucket), original(bucket, roles))[1],
    )

    _post(client)

    assert gesehen == ["chat"]
