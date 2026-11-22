"""F4: Die Schnittstelle für KI-Abos ist ab Werk aus (0.54, Päckchen AW)."""
import pytest

from app.config import Settings


def test_vorgabe_aus():
    felder = Settings.model_fields
    assert felder["mcp_aktiv"].default is False
    assert felder["mcp_oeffentliche_url"].default == ""


def test_app_ohne_einschalten_ohne_mcp_route():
    from app.config import settings
    from app.main import app

    if settings.mcp_aktiv:
        pytest.skip("lokale .env schaltet MCP ein — dann gibt es die Route zu Recht")
    assert app.state.mcp_server is None
    assert not [r for r in app.router.routes if getattr(r, "path", None) == "/mcp"]
