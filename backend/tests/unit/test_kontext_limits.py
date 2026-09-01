"""Such- und Anzeigelimit sind zwei verschiedene Zahlen.

Die 8 stammen aus der Oberfläche: Mehr Vorschläge deckten das Eingabefeld zu. Für einen
Assistenten ist die Trefferzahl dagegen keine Platz-, sondern eine Kostenfrage — und 8
sind dort zu wenig: Im Prüfsatz steht der erwartete Knoten in einem Fall auf Rang 9.

Beide hingen bis 08/2026 an derselben Einstellung; die tiefere Suche hätte deshalb das
Vorschlagsfenster geflutet. Seit 09/2026 berühren sie einander gar nicht mehr: Die
Anzeigezahl gilt nur noch für den Suchknopf (``POST /context/search``), weil eine Suche
des Assistenten kein Vorschlagsfenster mehr öffnet (ADR-017, Befund 7).
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


class TestKeineVorschlagsliste:
    """Der Werkzeugpfad kennt die Anzeigezahl nicht mehr (ADR-017, AP1).

    Bis 09/2026 kürzte er sein Ergebnis auf die Anzeigezahl und schickte es als
    SSE-Ereignis `context_suggestions` ins Vorschlagsfenster. Das Fenster ist aber ein
    Angebot an die Nutzer:in, Bausteine anzuheften — der Assistent hat sie längst
    gelesen. Wer nur eine Frage stellte, bekam ungefragt eine Auswahlliste über sein
    Eingabefeld gelegt.
    """

    def test_chat_router_kennt_die_anzeigezahl_nicht(self):
        import app.chat.router as router

        assert not hasattr(router, "anzeige_limit")
        assert not hasattr(router, "_fuer_vorschlagsliste")

    def test_kein_sse_ereignis_mehr(self):
        """Gegenprobe an der Quelle: Das Ereignis wird nirgends mehr erzeugt."""
        from pathlib import Path

        import app.chat.router as router

        assert "context_suggestions" not in Path(router.__file__).read_text(
            encoding="utf-8"
        )
