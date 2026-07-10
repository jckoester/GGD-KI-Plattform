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
import app.artifacts.store as store_mod
import app.export.document as doc_export_mod
from app.artifacts.router import router
from app.artifacts.store import QuotaExceeded
from app.export.pandoc import PandocUnavailable
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.session import get_db
from app.render.cache import svg_hash


def _user(sub="p", roles=("student",), grade="5") -> JwtPayload:
    return JwtPayload(sub=sub, roles=list(roles), grade=grade, jti="j", iat=1, exp=9999999999)


# ── promote_image ─────────────────────────────────────────────────────────────

async def test_promote_image_copies_bytes_and_prompt(monkeypatch):
    image_id = uuid4()
    conv_id = uuid4()
    record = SimpleNamespace(
        pseudonym="p", mime_type="image/png", conversation_id=conv_id, prompt="ein roter Fuchs"
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
    assert captured["title"] == "Bild"
    assert captured["origin_ref"] == f"image:{image_id}"
    assert captured["origin_conversation_id"] == conv_id


async def test_promote_image_foreign_owner_forbidden(monkeypatch):
    record = SimpleNamespace(pseudonym="jemand-anderes", mime_type="image/png",
                             conversation_id=uuid4(), prompt=None)
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
    record = SimpleNamespace(pseudonym="p", mime_type="image/png", conversation_id=uuid4(), prompt="x")
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
    assert captured["title"] == "Schaltplan"
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
    assert captured["title"] == "Funktionsgraph"


async def test_promote_diagram_render_error(monkeypatch):
    monkeypatch.setattr(
        promote.service, "render",
        AsyncMock(return_value={"svg": "<svg>err</svg>", "error": "TeX kaputt"}),
    )
    with pytest.raises(promote.PromotionError):
        await promote.promote_diagram(object(), user=_user(), kind="circuit", source="x")


async def test_promote_diagram_mermaid_uses_client_svg(monkeypatch):
    # mermaid wird NICHT serverseitig gerendert — der Client-SVG wird übernommen.
    render_spy = AsyncMock(side_effect=AssertionError("mermaid darf nicht serverseitig rendern"))
    monkeypatch.setattr(promote.service, "render", render_spy)
    monkeypatch.setattr(promote.store, "find_by_origin_ref", AsyncMock(return_value=None))
    captured = {}

    async def fake_save(db, **kw):
        captured.update(kw)
        return SimpleNamespace(id=uuid4(), **kw)

    monkeypatch.setattr(promote.store, "save_artifact", fake_save)

    await promote.promote_diagram(
        object(), user=_user(), kind="mermaid", source="graph TD; A-->B",
        svg="<svg>mermaid</svg>",
    )
    render_spy.assert_not_called()
    assert captured["kind"] == "mermaid"
    assert captured["data"] == b"<svg>mermaid</svg>"
    assert captured["mime_type"] == "image/svg+xml"
    assert captured["title"] == "Diagramm"


async def test_promote_diagram_mermaid_requires_svg(monkeypatch):
    with pytest.raises(promote.PromotionError):
        await promote.promote_diagram(object(), user=_user(), kind="mermaid", source="graph TD;", svg=None)


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
    )
    monkeypatch.setattr(store_mod, "list_artifacts", AsyncMock(return_value=[rec]))
    monkeypatch.setattr(store_mod, "used_bytes", AsyncMock(return_value=1234))
    monkeypatch.setattr(
        "app.artifacts.router.get_artifact_limits", lambda roles, grade: (365, 52428800)
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
