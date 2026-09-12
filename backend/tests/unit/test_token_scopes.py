"""Das Scope-Gatter — die einzige Stelle, an der ein Zugangstoken Zugang bekommt.

Geprüft wird die Zusage „was nicht in der Tabelle steht, ist gesperrt". Sie ist nicht
selbstverständlich: Die naheliegende Bauart wäre eine Sperrliste der verbotenen Pfade
gewesen, und die wäre bei jedem neuen Router stillschweigend zu eng geworden.
"""

import pytest

from app.auth.scopes import _ZUSTAENDIG, benoetigter_scope, pruefe_zugang
from app.auth.tokens import SCOPES
from fastapi import HTTPException


class TestWasEinTokenErreicht:
    @pytest.mark.parametrize("methode,pfad,erwartet", [
        ("GET", "/planning/groups/1/overview", "planning:read"),
        ("GET", "/planning", "planning:read"),
        ("PATCH", "/planning/slots/abc", "planning:write"),
        ("POST", "/planning/groups/1/units", "planning:write"),
        ("DELETE", "/planning/groups/1/units/x", "planning:write"),
        ("GET", "/context/nodes", "context:read"),
        ("PATCH", "/context/nodes/x", "context:write"),
        # Die Suche braucht einen Rumpf und ist deshalb POST — sie ändert nichts.
        ("POST", "/context/search", "context:read"),
    ])
    def test_zuordnung(self, methode, pfad, erwartet):
        assert benoetigter_scope(methode, pfad) == erwartet

    @pytest.mark.parametrize("pfad", [
        "/chat", "/chat/stream", "/budget", "/admin/flags", "/settings/users",
        "/assistants", "/auth/logout", "/review", "/access-requests/x",
        "/artifacts", "/render", "/calendar/sync", "/pii/scan", "/groups/me",
        # Unter `/context` hängt mehr als der Kontextspeicher. Diese beiden gehören der
        # Assistenten-Konfiguration bzw. dem Chat — ein Token hat dort nichts zu suchen.
        "/context/assistants/1/anchors", "/context/conversations/abc/nodes",
        # Und der Rest des Routers, den ein Spiegel nicht braucht.
        "/context/curricula/1", "/context/fachplan/by-subject/1",
        # Präfix-Ähnlichkeit darf nicht genügen: `/contextual` ist nicht `/context`.
        "/contextual", "/planningx", "/planning-extern", "/context/nodesX",
    ])
    def test_alles_andere_ist_gesperrt(self, pfad):
        assert benoetigter_scope("GET", pfad) is None
        with pytest.raises(HTTPException) as exc:
            pruefe_zugang(list(SCOPES), "GET", pfad)
        assert exc.value.status_code == 403


class TestSchreibenEnthaeltKeinLesen:
    """Absicht, kein Versehen: `write` impliziert `read` nicht."""

    def test_nur_schreibrecht_darf_nicht_lesen(self):
        with pytest.raises(HTTPException):
            pruefe_zugang(["planning:write"], "GET", "/planning/groups/1/overview")

    def test_nur_leserecht_darf_nicht_schreiben(self):
        with pytest.raises(HTTPException):
            pruefe_zugang(["planning:read"], "PATCH", "/planning/slots/x")

    def test_beide_zusammen_koennen_beides(self):
        pruefe_zugang(["planning:read", "planning:write"], "GET", "/planning/x")
        pruefe_zugang(["planning:read", "planning:write"], "PATCH", "/planning/x")

    def test_fremder_bereich_hilft_nicht(self):
        with pytest.raises(HTTPException):
            pruefe_zugang(["context:read", "context:write"], "GET", "/planning/x")


class TestTabelleUndScopesPassenZusammen:
    """Ein Scope, den die Tabelle nie verlangt, wäre eine Berechtigung ohne Wirkung —
    und ein verlangter Scope, den niemand vergeben kann, eine Tür ohne Schlüssel."""

    def test_jeder_scope_wird_irgendwo_verlangt(self):
        verlangt = {s for paar in _ZUSTAENDIG.values() for s in paar}
        assert verlangt == set(SCOPES), (
            f"nur in der Tabelle: {verlangt - set(SCOPES)}; "
            f"nur vergebbar: {set(SCOPES) - verlangt}"
        )

    def test_leere_scope_liste_kommt_nirgends_durch(self):
        for pfad in ("/planning/x", "/context/nodes", "/chat"):
            with pytest.raises(HTTPException):
                pruefe_zugang([], "GET", pfad)
