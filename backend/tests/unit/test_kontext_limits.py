"""Such- und Anzeigelimit sind zwei verschiedene Zahlen.

Die 8 stammen aus der Oberfläche: Mehr Vorschläge deckten das Eingabefeld zu. Für einen
Assistenten ist die Trefferzahl dagegen keine Platz-, sondern eine Kostenfrage — und 8
sind dort zu wenig: Im Prüfsatz steht der erwartete Knoten in einem Fall auf Rang 9.

Beide hingen bis 08/2026 an derselben Einstellung; die tiefere Suche hätte deshalb das
Vorschlagsfenster geflutet.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.preferences.service import (
    ANZEIGE_MAX,
    ANZEIGE_MIN,
    ANZEIGE_VORGABE,
    anzeige_limit,
)


async def _limit(prefs):
    with patch("app.preferences.service.get_preferences",
               new=AsyncMock(return_value=prefs)):
        return await anzeige_limit(object(), "p")


class TestAnzeigelimit:
    @pytest.mark.parametrize("prefs,erwartet", [
        ({"context_search_limit": 20}, 20),
        ({}, ANZEIGE_VORGABE),
        ({"context_search_limit": None}, ANZEIGE_VORGABE),
        ({"context_search_limit": "keine Zahl"}, ANZEIGE_VORGABE),
        ({"context_search_limit": 1}, ANZEIGE_MIN),
        ({"context_search_limit": 999}, ANZEIGE_MAX),
        ({"context_search_limit": "12"}, 12),
    ])
    async def test_grenzen_und_rueckfall(self, prefs, erwartet):
        assert await _limit(prefs) == erwartet

    async def test_liefert_eine_zahl_kein_dict(self):
        """Der Grund für die Funktion: Das Einstellungs-Dict enthält unter anderem das
        WebUntis-Kürzel und darf modellnahe Module nicht erreichen."""
        assert isinstance(await _limit({"context_search_limit": 9, "untis_kuerzel": "MUS"}), int)


class TestSuchtiefeDesAssistenten:
    async def test_werkzeug_nutzt_die_zentrale_zahl(self):
        """Nicht die Anzeigezahl aus dem Profil — sonst deckelte die Oberfläche die Suche."""
        from app.chat import router

        with patch.object(router.settings, "assistant_context_limit", 20), \
             patch.object(router, "_resolve_conversation_subject_id",
                          new=AsyncMock(return_value=None)), \
             patch.object(router, "_exec_search_context_nodes",
                          new=AsyncMock(return_value=[])) as suche:
            ctx = router.ToolContext(db=object(), user=type("U", (), {"sub": "p"})(),
                                     group_id=None, conversation_id=None)
            await router._search_context_nodes_handler({"query": "x"}, ctx)

        assert suche.await_args.kwargs["limit"] == 20

    def test_vorgabe_deckt_den_pruefsatz_ab(self):
        """Im Prüfsatz steht der erwartete Knoten in einem Fall auf Rang 9 — mit der
        Anzeigezahl 8 wäre er für den Assistenten unsichtbar."""
        from app.config import settings

        assert settings.assistant_context_limit > ANZEIGE_VORGABE
        assert settings.assistant_context_limit >= 10


class TestVorschlagsliste:
    """Was der Assistent findet, ist nicht, was die Oberfläche zeigt."""

    def test_wird_auf_die_anzeigezahl_gekuerzt(self):
        from app.chat.router import _fuer_vorschlagsliste

        treffer = [{"node_id": str(i)} for i in range(20)]
        assert len(_fuer_vorschlagsliste(treffer, 8)) == 8

    def test_kuerzere_liste_bleibt_unangetastet(self):
        from app.chat.router import _fuer_vorschlagsliste

        treffer = [{"node_id": "a"}, {"node_id": "b"}]
        assert _fuer_vorschlagsliste(treffer, 8) == treffer

    def test_reihenfolge_bleibt(self):
        """Gekürzt wird am Ende — die besten Treffer stehen vorn und müssen bleiben."""
        from app.chat.router import _fuer_vorschlagsliste

        treffer = [{"node_id": str(i)} for i in range(20)]
        assert [t["node_id"] for t in _fuer_vorschlagsliste(treffer, 3)] == ["0", "1", "2"]
