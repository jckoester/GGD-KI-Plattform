"""Unit-Tests: Promotion von Chat-Inhalten in die Artefaktbibliothek (Phase 18, Schritt 2).

Deckt die Promotion-Service-Funktionen (`app.artifacts.promote`) und die HTTP-Fehlerabbildung
der Endpunkte (`/artifacts/from-image`, `/artifacts/from-diagram`) ab. Bytes-Persistenz + Quota
liegen in `app.artifacts.store` (test_artifact_store.py); hier werden Store/Render gemockt.
"""
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-school-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

import app.artifacts.promote as promote
import app.artifacts.router as artifacts_router
import app.artifacts.store as store_mod
import app.export.document as doc_export_mod
from app.artifacts.router import router
from app.artifacts.store import QuotaExceeded
from app.export.pandoc import PandocUnavailable


def _stub_templates(monkeypatch):
    """Schulweite Vorlagen (Schritt 6) neutralisieren — kein DB/Filesystem im Export-Test."""
    monkeypatch.setattr(artifacts_router.export_templates, "get_export_css", AsyncMock(return_value=""))
    monkeypatch.setattr(artifacts_router.export_templates, "vorlage", lambda fmt: None)
    # Vorgabe: Herkunftszeile aus — ein Update ändert bestehende Exporte nicht von selbst.
    monkeypatch.setattr(
        artifacts_router.export_templates, "get_export_provenance", AsyncMock(return_value=False)
    )
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db
from app.render.cache import svg_hash


@pytest.fixture(autouse=True)
def _ohne_herkunft(monkeypatch):
    """Die Herkunft fragt die Datenbank (0.41); hier steht nur `object()`. Tests, die sie
    prüfen, setzen sie selbst."""
    monkeypatch.setattr(promote, "herkunft", AsyncMock(return_value=promote.KEINE_HERKUNFT))
    monkeypatch.setattr(promote, "frage_zur_nachricht", AsyncMock(return_value=None))


def _user(sub="p", roles=("student",), grade="5") -> JwtPayload:
    return JwtPayload(sub=sub, roles=list(roles), grade=grade, jti="j", iat=1, exp=9999999999)


# ── promote_image ─────────────────────────────────────────────────────────────

async def test_promote_image_copies_bytes_and_prompt(monkeypatch):
    image_id = uuid4()
    conv_id = uuid4()
    record = SimpleNamespace(
        pseudonym="p", mime_type="image/png", conversation_id=conv_id,
        prompt="ein roter Fuchs", provider_model="openai/black-forest-labs/FLUX.1-schnell",
    )
    monkeypatch.setattr(promote.image_store, "get_image_record", AsyncMock(return_value=record))
    monkeypatch.setattr(promote.image_store, "read_image_bytes", lambda r: b"PNGDATA")
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)

    art, created = await promote.promote_image(object(), user=_user(), image_id=image_id)

    assert created is True
    assert captured["kind"] == "image"
    assert captured["mime_type"] == "image/png"
    assert captured["data"] == b"PNGDATA"
    assert captured["source"] == "ein roter Fuchs"          # Prompt → source
    assert captured["title"] == "ein roter Fuchs"            # Titel aus dem Prompt (0.41)
    assert captured["origin_ref"] == f"image:{image_id}"
    assert captured["origin_conversation_id"] == conv_id


async def test_promote_image_foreign_owner_forbidden(monkeypatch):
    record = SimpleNamespace(pseudonym="jemand-anderes", mime_type="image/png",
                             conversation_id=uuid4(), prompt=None, provider_model=None)
    monkeypatch.setattr(promote.image_store, "get_image_record", AsyncMock(return_value=record))
    with pytest.raises(PermissionError):
        await promote.promote_image(object(), user=_user(sub="p"), image_id=uuid4())


async def test_promote_image_missing_record(monkeypatch):
    monkeypatch.setattr(promote.image_store, "get_image_record", AsyncMock(return_value=None))
    with pytest.raises(promote.PromotionError):
        await promote.promote_image(object(), user=_user(), image_id=uuid4())


async def test_promote_image_missing_file(monkeypatch):
    record = SimpleNamespace(pseudonym="p", mime_type="image/png", conversation_id=uuid4(), prompt=None)
    monkeypatch.setattr(promote.image_store, "get_image_record", AsyncMock(return_value=record))
    monkeypatch.setattr(promote.image_store, "read_image_bytes", lambda r: None)
    with pytest.raises(promote.PromotionError):
        await promote.promote_image(object(), user=_user(), image_id=uuid4())


async def test_promote_image_idempotent(monkeypatch):
    record = SimpleNamespace(pseudonym="p", mime_type="image/png",
                             conversation_id=uuid4(), prompt="x", provider_model=None)
    existing = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(promote.image_store, "get_image_record", AsyncMock(return_value=record))
    monkeypatch.setattr(promote.image_store, "read_image_bytes", lambda r: b"x")
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=existing))
    monkeypatch.setattr(promote.store, "save_artifact", AsyncMock(return_value=existing))

    art, created = await promote.promote_image(object(), user=_user(), image_id=uuid4())
    assert created is False        # war bereits in der Bibliothek


# ── promote_diagram ───────────────────────────────────────────────────────────

async def test_promote_diagram_circuit_server_renders(monkeypatch):
    source = "\\draw (0,0) to[R] (2,0);"
    monkeypatch.setattr(
        promote.service, "render",
        AsyncMock(return_value={"svg": "<svg>circuit</svg>", "error": None, "cached": False}),
    )
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)

    art, created = await promote.promote_diagram(
        object(), user=_user(), kind="circuit", source=source
    )

    assert created is True
    assert captured["kind"] == "circuit"
    assert captured["mime_type"] == "image/svg+xml"
    assert captured["data"] == b"<svg>circuit</svg>"     # serverseitig gerendert
    assert captured["source"] == source                   # roher Quelltext bewahrt
    # Ohne Titel in der Quelle und ohne Frage: Art und Datum (0.41).
    assert captured["title"].startswith("Schaltplan vom ")
    assert captured["origin_ref"] == f"circuit:{svg_hash('circuit', source)}"


async def test_promote_diagram_plot_title(monkeypatch):
    monkeypatch.setattr(
        promote.service, "render",
        AsyncMock(return_value={"svg": "<svg>plot</svg>", "error": None}),
    )
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    await promote.promote_diagram(object(), user=_user(), kind="plot", source="functions: []")
    # Ohne Titel in der Quelle und ohne Frage: Art und Datum (0.41).
    assert captured["title"].startswith("Funktionsgraph vom ")


async def test_promote_diagram_smiles_wird_serverseitig_gerendert(monkeypatch):
    """Strukturformel (0.30): wie Schaltplan und Graph — der Server zeichnet aus der Quelle,
    ein mitgeschicktes SVG wird nicht gebraucht."""
    render = AsyncMock(return_value={"svg": "<svg>mol</svg>", "error": None})
    monkeypatch.setattr(promote.service, "render", render)
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    await promote.promote_diagram(object(), user=_user(), kind="smiles", source="CCO")
    # Ohne Titel in der Quelle und ohne Frage: Art und Datum (0.41).
    assert captured["title"].startswith("Strukturformel vom ")
    assert render.await_args.args[1:] == ("smiles", "CCO")


async def test_promote_diagram_render_error(monkeypatch):
    monkeypatch.setattr(
        promote.service, "render",
        AsyncMock(return_value={"svg": "<svg>err</svg>", "error": "TeX kaputt"}),
    )
    with pytest.raises(promote.PromotionError):
        await promote.promote_diagram(object(), user=_user(), kind="circuit", source="x")


async def test_promote_diagram_mermaid_rendert_serverseitig(monkeypatch):
    """Seit 0.36 (Pele im Sidecar) wie die anderen Diagramme: aus der Quelle neu gerendert; ein
    mitgeschicktes Browser-SVG zählt nicht."""
    render_spy = AsyncMock(return_value={"svg": "<svg>pele</svg>", "error": None, "cached": False})
    monkeypatch.setattr(promote.service, "render", render_spy)
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)

    await promote.promote_diagram(
        object(), user=_user(), kind="mermaid", source="graph TD; A-->B",
        svg="<svg>vom Browser</svg>",
    )
    render_spy.assert_awaited_once()
    assert render_spy.await_args.args[1:] == ("mermaid", "graph TD; A-->B")
    assert captured["kind"] == "mermaid"
    assert captured["data"] == b"<svg>pele</svg>"
    assert captured["mime_type"] == "image/svg+xml"
    # Ohne Titel in der Quelle und ohne Frage: Art und Datum (0.41).
    assert captured["title"].startswith("Diagramm vom ")


async def test_promote_diagram_mermaid_renderfehler(monkeypatch):
    monkeypatch.setattr(promote.service, "render",
                        AsyncMock(return_value={"svg": "<svg/>", "error": "Parse error", "cached": False}))
    with pytest.raises(promote.PromotionError):
        await promote.promote_diagram(object(), user=_user(), kind="mermaid", source="graph TD;")


async def test_promote_diagram_empty_source():
    with pytest.raises(promote.PromotionError):
        await promote.promote_diagram(object(), user=_user(), kind="circuit", source="   ")


async def test_promote_diagram_unknown_kind():
    with pytest.raises(promote.PromotionError):
        await promote.promote_diagram(object(), user=_user(), kind="banana", source="x")


# ── Endpunkte: HTTP-Fehlerabbildung ───────────────────────────────────────────

def _client(monkeypatch, user=None):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app)


def test_endpoint_from_image_ok(monkeypatch):
    art = SimpleNamespace(
        id=uuid4(), kind="image", mime_type="image/png", title="Bild", byte_size=7,
        created_at="2026-07-07T00:00:00+00:00", expires_at="2027-07-07T00:00:00+00:00",
    )
    monkeypatch.setattr(promote, "promote_image", AsyncMock(return_value=(art, True)))
    client = _client(monkeypatch)
    resp = client.post("/artifacts/from-image", json={"image_id": str(uuid4())})
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True and body["kind"] == "image"


def test_endpoint_from_image_forbidden(monkeypatch):
    monkeypatch.setattr(promote, "promote_image", AsyncMock(side_effect=PermissionError()))
    client = _client(monkeypatch)
    resp = client.post("/artifacts/from-image", json={"image_id": str(uuid4())})
    assert resp.status_code == 403


def test_endpoint_from_image_quota(monkeypatch):
    monkeypatch.setattr(promote, "promote_image", AsyncMock(side_effect=QuotaExceeded("voll")))
    client = _client(monkeypatch)
    resp = client.post("/artifacts/from-image", json={"image_id": str(uuid4())})
    assert resp.status_code == 409


def test_endpoint_from_diagram_unknown_kind(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/artifacts/from-diagram", json={"kind": "banana", "source": "x"})
    assert resp.status_code == 422


def test_endpoint_from_diagram_ok(monkeypatch):
    art = SimpleNamespace(
        id=uuid4(), kind="plot", mime_type="image/svg+xml", title="Funktionsgraph", byte_size=12,
        created_at="2026-07-07T00:00:00+00:00", expires_at="2027-07-07T00:00:00+00:00",
    )
    monkeypatch.setattr(promote, "promote_diagram", AsyncMock(return_value=(art, False)))
    client = _client(monkeypatch)
    resp = client.post("/artifacts/from-diagram", json={"kind": "plot", "source": "functions: []"})
    assert resp.status_code == 200
    assert resp.json()["created"] is False


# ── GET /artifacts/{id}: SVG-Härtung ──────────────────────────────────────────

def test_get_svg_artifact_is_hardened(monkeypatch):
    rec = SimpleNamespace(owner_pseudonym="p", mime_type="image/svg+xml")
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    monkeypatch.setattr(store_mod, "read_artifact_bytes", lambda r: b"<svg/>")
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}")
    assert resp.status_code == 200
    assert "sandbox" in resp.headers["content-security-policy"]
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_get_png_artifact_not_hardened(monkeypatch):
    rec = SimpleNamespace(owner_pseudonym="p", mime_type="image/png")
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    monkeypatch.setattr(store_mod, "read_artifact_bytes", lambda r: b"PNG")
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}")
    assert resp.status_code == 200
    assert "content-security-policy" not in resp.headers


def test_get_foreign_artifact_forbidden(monkeypatch):
    rec = SimpleNamespace(owner_pseudonym="jemand-anderes", mime_type="image/png")
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}")
    assert resp.status_code == 403


# ── GET /artifacts (Liste + Quota) & DELETE ───────────────────────────────────

def test_list_library_returns_items_and_usage(monkeypatch):
    from datetime import datetime, timezone
    ts = datetime(2026, 7, 8, tzinfo=timezone.utc)
    rec = SimpleNamespace(
        id=uuid4(), kind="plot", mime_type="image/svg+xml", title="Funktionsgraph",
        byte_size=1234, source="functions: []", created_at=ts, expires_at=ts,
        provider_model=None, subject_id=None, topic=None, updated_at=ts, assistant_name=None,
    )
    monkeypatch.setattr(store_mod, "list_artifacts", AsyncMock(return_value=[rec]))
    monkeypatch.setattr(store_mod, "used_bytes", AsyncMock(return_value=1234))
    monkeypatch.setattr(
        "app.artifacts.router.get_artifact_limits", lambda roles, grade: (365, 52428800)
    )
    monkeypatch.setattr(store_mod, "count_artifacts", AsyncMock(return_value=1))
    monkeypatch.setattr(store_mod, "facetten", AsyncMock(return_value=([], [])))
    # Die Übernahme-Zuordnung (AP8) fragt die DB; hier steht nur ein MagicMock.
    monkeypatch.setattr(
        "app.artifacts.uebernahme.bausteine_zu_artefakten", AsyncMock(return_value={})
    )
    client = _client(monkeypatch)
    resp = client.get("/artifacts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["used_bytes"] == 1234
    assert body["quota_bytes"] == 52428800
    assert len(body["items"]) == 1
    assert body["items"][0]["source"] == "functions: []"
    assert body["items"][0]["kind"] == "plot"
    # Ein Funktionsgraph lässt sich nicht übernehmen (AP8) und hat keinen Baustein.
    assert body["items"][0]["uebernehmbar"] is False
    assert body["items"][0]["baustein_id"] is None


def test_delete_artifact_owner_ok(monkeypatch):
    rec = SimpleNamespace(owner_pseudonym="p", mime_type="image/png")
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    deleted = AsyncMock()
    monkeypatch.setattr(store_mod, "delete_artifact", deleted)
    client = _client(monkeypatch)
    resp = client.request("DELETE", f"/artifacts/{uuid4()}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    deleted.assert_awaited_once()


def test_delete_artifact_foreign_forbidden(monkeypatch):
    rec = SimpleNamespace(owner_pseudonym="jemand-anderes", mime_type="image/png")
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    deleted = AsyncMock()
    monkeypatch.setattr(store_mod, "delete_artifact", deleted)
    client = _client(monkeypatch)
    resp = client.request("DELETE", f"/artifacts/{uuid4()}")
    assert resp.status_code == 403
    deleted.assert_not_called()


def test_delete_artifact_missing_404(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=None))
    client = _client(monkeypatch)
    resp = client.request("DELETE", f"/artifacts/{uuid4()}")
    assert resp.status_code == 404


# ── GeoGebra-Export (Schritt 4) ───────────────────────────────────────────────

def test_ggb_from_source_ok(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/artifacts/ggb", json={"source": "functions:\n  - x^2\n", "title": "Parabel"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.geogebra.file"
    assert "parabel.ggb" in resp.headers["content-disposition"]
    assert resp.content[:2] == b"PK"   # ZIP-Signatur


def test_ggb_from_source_invalid_422(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/artifacts/ggb", json={"source": "kein plot"})
    assert resp.status_code == 422


def test_ggb_from_artifact_ok(monkeypatch):
    rec = SimpleNamespace(
        owner_pseudonym="p", kind="plot", source="functions:\n  - x^2\n", title="Parabel",
    )
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}/ggb")
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"


def test_ggb_from_artifact_wrong_kind_422(monkeypatch):
    rec = SimpleNamespace(owner_pseudonym="p", kind="circuit", source="...", title="x")
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}/ggb")
    assert resp.status_code == 422


def test_ggb_from_artifact_foreign_403(monkeypatch):
    rec = SimpleNamespace(owner_pseudonym="anders", kind="plot", source="functions:\n  - x\n", title="x")
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=rec))
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}/ggb")
    assert resp.status_code == 403


# ── Dokumente (Material-Werkstatt, Phase 19) ──────────────────────────────────

def _doc(**kw):
    from datetime import datetime, timezone
    ts = datetime(2026, 7, 9, tzinfo=timezone.utc)
    base = dict(
        id=uuid4(), owner_pseudonym="p", kind="document", mime_type="text/markdown",
        title="Arbeitsblatt", source="# Titel", byte_size=7, created_at=ts, expires_at=ts,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_create_document_ok(monkeypatch):
    monkeypatch.setattr(store_mod, "create_document", AsyncMock(return_value=_doc()))
    client = _client(monkeypatch)
    resp = client.post("/artifacts/document", json={"title": "AB", "markdown": "# Titel"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True and body["kind"] == "document"


def test_create_document_quota(monkeypatch):
    monkeypatch.setattr(store_mod, "create_document", AsyncMock(side_effect=QuotaExceeded("voll")))
    client = _client(monkeypatch)
    resp = client.post("/artifacts/document", json={"markdown": "x"})
    assert resp.status_code == 409


def test_get_document_ok(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(source="# Hallo")))
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}/document")
    assert resp.status_code == 200
    assert resp.json()["source"] == "# Hallo"


def test_get_document_wrong_kind_422(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(kind="image")))
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}/document")
    assert resp.status_code == 422


def test_get_document_foreign_403(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(owner_pseudonym="x")))
    client = _client(monkeypatch)
    resp = client.get(f"/artifacts/{uuid4()}/document")
    assert resp.status_code == 403


def test_update_document_ok(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc()))
    monkeypatch.setattr(store_mod, "update_document", AsyncMock(return_value=_doc(title="Neu")))
    client = _client(monkeypatch)
    resp = client.put(f"/artifacts/{uuid4()}", json={"title": "Neu", "markdown": "# Neu"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is False and body["title"] == "Neu"


def test_update_document_wrong_kind_422(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(kind="plot")))
    client = _client(monkeypatch)
    resp = client.put(f"/artifacts/{uuid4()}", json={"markdown": "x"})
    assert resp.status_code == 422


def test_update_document_foreign_403(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(owner_pseudonym="x")))
    client = _client(monkeypatch)
    resp = client.put(f"/artifacts/{uuid4()}", json={"markdown": "x"})
    assert resp.status_code == 403


# ── Dokument-Export (Schritt 4) ───────────────────────────────────────────────

def test_export_download(monkeypatch):
    _stub_templates(monkeypatch)
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(title="Mein AB")))
    monkeypatch.setattr(
        doc_export_mod, "export_document",
        AsyncMock(return_value=(b"%PDF-1.7 ...", "application/pdf")),
    )
    client = _client(monkeypatch)
    resp = client.post(f"/artifacts/{uuid4()}/export?format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "mein-ab.pdf" in resp.headers["content-disposition"]
    assert resp.content[:5] == b"%PDF-"


def test_export_save_returns_json(monkeypatch):
    _stub_templates(monkeypatch)
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc()))
    monkeypatch.setattr(
        doc_export_mod, "export_document",
        AsyncMock(return_value=(b"PKdocx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
    )
    saved = _doc(kind="export_docx", mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    monkeypatch.setattr(store_mod, "save_artifact", AsyncMock(return_value=saved))
    client = _client(monkeypatch)
    resp = client.post(f"/artifacts/{uuid4()}/export?format=docx&save=true")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True and body["kind"] == "export_docx"


def test_export_wrong_kind_422(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(kind="image")))
    client = _client(monkeypatch)
    resp = client.post(f"/artifacts/{uuid4()}/export?format=pdf")
    assert resp.status_code == 422


def test_export_bad_format_422(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc()))
    client = _client(monkeypatch)
    resp = client.post(f"/artifacts/{uuid4()}/export?format=txt")
    assert resp.status_code == 422   # Query-Pattern lehnt txt ab


def test_export_office_unavailable_503(monkeypatch):
    _stub_templates(monkeypatch)
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc()))
    monkeypatch.setattr(
        doc_export_mod, "export_document",
        AsyncMock(side_effect=PandocUnavailable("weg")),
    )
    client = _client(monkeypatch)
    resp = client.post(f"/artifacts/{uuid4()}/export?format=docx")
    assert resp.status_code == 503


def test_export_foreign_403(monkeypatch):
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc(owner_pseudonym="x")))
    client = _client(monkeypatch)
    resp = client.post(f"/artifacts/{uuid4()}/export?format=pdf")
    assert resp.status_code == 403


def test_export_passes_school_templates(monkeypatch, tmp_path):
    # Schulweite Vorlagen (Schritt 6) müssen in export_document durchgereicht werden.
    import app.artifacts.router as artifacts_router
    monkeypatch.setattr(store_mod, "get_artifact", AsyncMock(return_value=_doc()))
    monkeypatch.setattr(
        artifacts_router.export_templates, "get_export_provenance", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(artifacts_router.export_templates, "get_export_css", AsyncMock(return_value="h1{color:navy}"))
    ref = tmp_path / "reference.docx"; ref.write_bytes(b"PK")
    monkeypatch.setattr(artifacts_router.export_templates, "reference_path", lambda fmt: ref if fmt == "docx" else None)
    captured = {}

    async def fake_export(db, **kw):
        captured.update(kw)
        return b"PKdocx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    monkeypatch.setattr(doc_export_mod, "export_document", fake_export)
    resp = _client(monkeypatch).post(f"/artifacts/{uuid4()}/export?format=docx")
    assert resp.status_code == 200
    assert captured["reference_doc"] == str(ref)
    # CSS wird nur für PDF gelesen — bei DOCX leer
    assert captured["extra_css"] == ""


async def test_promote_image_kopiert_die_herkunft(monkeypatch):
    """Der Kern von Alembic 0050: Das Artefakt überlebt die Konversation, die Bildzeile nicht.

    Ohne diese Kopie wäre die Herkunft nach spätestens 93 Tagen weg — ausgerechnet bei den
    Artefakten, die in Arbeitsblättern und Facharbeiten landen.
    """
    record = SimpleNamespace(
        pseudonym="p", mime_type="image/png", conversation_id=uuid4(),
        prompt="ein roter Fuchs", provider_model="mistral/mistral-small-latest",
    )
    monkeypatch.setattr(promote.image_store, "get_image_record", AsyncMock(return_value=record))
    monkeypatch.setattr(promote.image_store, "read_image_bytes", lambda r: b"PNG")
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    monkeypatch.setattr(promote, "herkunft", AsyncMock(return_value=promote.Herkunft(
        None, record.conversation_id, 9, "Bilder für den Unterricht",
    )))
    await promote.promote_image(object(), user=_user(), image_id=uuid4())

    assert captured["provider_model"] == "mistral/mistral-small-latest"
    assert (captured["subject_id"], captured["assistant_name"]) == (9, "Bilder für den Unterricht")


async def test_promote_image_ohne_herkunft_bleibt_leer(monkeypatch):
    """Alt-Bilder haben keine — ein geratener Wert wäre in einer Quellenangabe schlimmer."""
    record = SimpleNamespace(pseudonym="p", mime_type="image/png",
                             conversation_id=uuid4(), prompt="x", provider_model=None)
    monkeypatch.setattr(promote.image_store, "get_image_record", AsyncMock(return_value=record))
    monkeypatch.setattr(promote.image_store, "read_image_bytes", lambda r: b"PNG")
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    await promote.promote_image(object(), user=_user(), image_id=uuid4())

    assert captured["provider_model"] is None


# ── Herkunft über die Nachrichten-ID (Modell-Transparenz) ─────────────────────
#
# Diagramme und Dokumente entstehen aus dem Text einer Chat-Antwort. Das Modell dahinter
# kennt nur das Backend — deshalb schickt der Client die Nachrichten-ID, nicht den
# Modellnamen. Eine Client-Behauptung in einer Quellenangabe wäre wertlos.

def _db_mit_zeile(zeile):
    db = MagicMock()
    ergebnis = MagicMock()
    ergebnis.first.return_value = zeile
    db.execute = AsyncMock(return_value=ergebnis)
    return db


async def test_herkunft_wird_ueber_die_nachricht_ermittelt(monkeypatch):
    monkeypatch.undo()   # die echte Funktion, nicht die Vorgabe der Fixture
    conv = uuid4()
    db = _db_mit_zeile(("openai/openai/gpt-oss-120b", conv, 7, "Stundenentwurf"))

    treffer = await promote.herkunft(db, pseudonym="p", message_id=uuid4())

    assert treffer == promote.Herkunft("openai/openai/gpt-oss-120b", conv, 7, "Stundenentwurf")
    db.execute.assert_awaited_once()


async def test_herkunft_ohne_id_fragt_die_datenbank_nicht(monkeypatch):
    monkeypatch.undo()
    db = MagicMock()
    db.execute = AsyncMock()

    assert await promote.herkunft(db, pseudonym="p") == promote.KEINE_HERKUNFT
    db.execute.assert_not_awaited()


async def test_fremde_nachricht_liefert_keine_herkunft(monkeypatch):
    """Die Abfrage bindet an die Konversation der Nutzer:in.

    Über eine fremde ID ließe sich sonst zwar kein Inhalt lesen, aber erraten, welches
    Modell, Fach und welcher Assistent dort im Einsatz waren.
    """
    monkeypatch.undo()
    db = _db_mit_zeile(None)   # Join greift nicht

    assert await promote.herkunft(db, pseudonym="p", message_id=uuid4()) == promote.KEINE_HERKUNFT


async def test_promote_diagram_uebernimmt_die_herkunft(monkeypatch):
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    conv = uuid4()
    monkeypatch.setattr(promote, "herkunft", AsyncMock(return_value=promote.Herkunft(
        "mistral/mistral-small-latest", conv, 4, "Mathe-Aufgaben",
    )))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    monkeypatch.setattr(promote.service, "render",
                        AsyncMock(return_value={"svg": "<svg>x</svg>", "error": None, "cached": False}))
    await promote.promote_diagram(
        object(), user=_user(), kind="mermaid", source="graph TD; A-->B", message_id=uuid4(),
    )

    assert captured["provider_model"] == "mistral/mistral-small-latest"
    # Seit 0.41 auch Chat, Fach und Assistent — bis dahin blieb `origin_conversation_id` leer.
    assert captured["origin_conversation_id"] == conv
    assert captured["subject_id"] == 4
    assert captured["assistant_name"] == "Mathe-Aufgaben"


async def test_promote_diagram_ohne_nachricht_bleibt_ohne_herkunft(monkeypatch):
    """Etwa beim Speichern aus einer alten Konversation ohne Nachrichten-ID."""
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    monkeypatch.setattr(promote.service, "render",
                        AsyncMock(return_value={"svg": "<svg>x</svg>", "error": None, "cached": False}))
    await promote.promote_diagram(
        object(), user=_user(), kind="mermaid", source="graph TD; A-->B"
    )

    assert captured["provider_model"] is None


# ── Herkunftszeile im Export (Modell-Transparenz, Schritt 6) ──────────────────

def test_herkunftszeile_nennt_werkzeug_modell_und_datum():
    from app.export.document import herkunftszeile

    zeile = herkunftszeile(werkzeug="ki@ggd", modell="gpt-oss-120b", zeitpunkt="29.08.2026")

    assert zeile == "Erstellt mit ki@ggd · Modell gpt-oss-120b · 29.08.2026"


def test_ohne_modell_keine_herkunftszeile():
    """Ein von Hand geschriebenes Dokument darf nicht „Erstellt mit …" tragen.

    Die Werkstatt lässt sich auch ganz ohne KI benutzen — eine pauschale Zeile wäre dort
    eine Falschangabe.
    """
    from app.export.document import herkunftszeile

    assert herkunftszeile(werkzeug="ki@ggd", modell=None, zeitpunkt="29.08.2026") is None


def test_herkunftszeile_wird_abgesetzt_angehaengt():
    from app.export.document import _mit_herkunft

    ergebnis = _mit_herkunft("# Titel\n\nInhalt", "Erstellt mit ki@ggd")

    assert ergebnis.startswith("# Titel\n\nInhalt")
    assert ergebnis.rstrip().endswith("*Erstellt mit ki@ggd*")
    assert "---" in ergebnis          # sichtbar vom Inhalt getrennt


def test_ohne_herkunft_bleibt_das_markdown_unveraendert():
    from app.export.document import _mit_herkunft

    assert _mit_herkunft("# Titel", None) == "# Titel"


def test_ohne_werkzeugnamen_nur_modell_und_datum():
    """„Erstellt mit dieser Plattform" hilft in einem exportierten Dokument niemandem."""
    from app.export.document import herkunftszeile

    assert herkunftszeile(werkzeug=None, modell="gpt-oss-120b", zeitpunkt="29.08.2026") == (
        "Modell gpt-oss-120b · 29.08.2026"
    )


async def test_promote_diagram_titel_aus_der_frage(monkeypatch):
    """0.41, F6: Ein Schaltplan kennt keinen Titel — dann die Frage, die ihn auslöste."""
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    monkeypatch.setattr(promote, "frage_zur_nachricht",
                        AsyncMock(return_value="Zeichne zwei Lampen in Reihe"))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    monkeypatch.setattr(promote.service, "render",
                        AsyncMock(return_value={"svg": "<svg>x</svg>", "error": None, "cached": False}))
    await promote.promote_diagram(object(), user=_user(), kind="circuit", source="\\draw", message_id=uuid4())

    assert captured["title"] == "Zeichne zwei Lampen in Reihe"


async def test_ausdruecklicher_titel_geht_vor(monkeypatch):
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)
    monkeypatch.setattr(promote.service, "render",
                        AsyncMock(return_value={"svg": "<svg>x</svg>", "error": None, "cached": False}))
    await promote.promote_diagram(object(), user=_user(), kind="mermaid",
                                  source="pie title Anteile\n A: 1", title="Mein Titel")

    assert captured["title"] == "Mein Titel"
