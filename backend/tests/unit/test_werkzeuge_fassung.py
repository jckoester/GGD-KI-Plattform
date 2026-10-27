"""Päckchen AE, Schritt 1 (27.10.2026): Die Chat-Werkzeuge geben die Stufe der Person ins
Suchprofil — `Suchprofil.grade` entscheidet, welche Bildungsplan-Fassung gilt
(`search._auf_geltende_fassung`). Vorher fehlte sie in allen drei, und `list_context_nodes`
lieferte „erklären“ in jeder Fassung jedes Fachs.

Die Stufe kommt aus `stufe_der_person` (Gruppe der Konversation, sonst Anmeldung) — dieselbe
Quelle wie die Zeile im Systemtext (F2: über die Stufe der Gruppe, auch für Lehrkräfte).
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.chat import router
from app.context.search import Abschnitt, Suchergebnis

pytestmark = pytest.mark.asyncio


def _ctx():
    return router.ToolContext(db=MagicMock(), user=SimpleNamespace(sub="p", roles=["student"], grade="7"),
                              group_id=None, conversation_id=None)


@pytest.mark.parametrize("stufe", [7, None])
async def test_list_context_nodes(stufe):
    with patch.object(router, "stufe_der_person", new=AsyncMock(return_value=stufe)), \
         patch.object(router, "aufzaehlung", new=AsyncMock(return_value=Abschnitt(gesamt=0))) as auf, \
         patch.object(router, "abgrenzungen_zu", new=AsyncMock(return_value={})), \
         patch.object(router, "_subject_id_aus_name", new=AsyncMock(return_value=None)):
        await router._list_context_nodes_handler({"titel": "erklären", "content_type": "operator"}, _ctx())
    profil = auf.await_args.args[1]
    assert profil.grade == stufe
    # Kein stiller Fachfilter (Handler-Warnung): ohne Fachangabe über alle Fächer.
    assert auf.await_args.args[0].subject_id is None


@pytest.mark.parametrize("stufe", [9, None])
async def test_get_operatoren(stufe):
    with patch.object(router, "stufe_der_person", new=AsyncMock(return_value=stufe)), \
         patch.object(router, "_resolve_conversation_subject_id", new=AsyncMock(return_value=6)), \
         patch.object(router, "aufzaehlung", new=AsyncMock(return_value=Abschnitt(gesamt=0))) as auf:
        await router._exec_get_operatoren(_ctx())
    assert auf.await_args.args[1].grade == stufe


@pytest.mark.parametrize("stufe", [11, None])
async def test_search_context_nodes(stufe):
    ergebnis = Suchergebnis(identifikation=Abschnitt(gesamt=0), thematisch=Abschnitt(gesamt=0))
    with patch.object(router, "stufe_der_person", new=AsyncMock(return_value=stufe)), \
         patch.object(router, "_resolve_conversation_subject_id", new=AsyncMock(return_value=None)), \
         patch.object(router, "suche", new=AsyncMock(return_value=ergebnis)) as such, \
         patch.object(router, "abgrenzungen_zu", new=AsyncMock(return_value={})), \
         patch.object(router, "bp_baender_zu", new=AsyncMock(return_value={})):
        await router._search_context_nodes_handler({"query": "erklären"}, _ctx())
    assert such.await_args.args[1].grade == stufe
