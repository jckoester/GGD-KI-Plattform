"""Hinweis im Strom, wenn die Vorliebe nicht anwendbar war (0.51, Päckchen AV Schritt 12).

`vorliebe_anwenden` liefert neben dem Modell einen Grund; der Chat reicht ihn als
`event: modell_hinweis` an die Oberfläche — mit dem Modell, das tatsächlich antwortet.
Die Regeln selbst prüft `test_modellwahl.py`, das Anlegen `tests/integration/test_chat_modellwahl.py`.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.auth.jwt import JwtPayload
from app.chat.router import chat
from app.chat.schemas import ChatRequest

from .test_chat_models import _FakeHttpClient, _make_execute_mock, _reset_model_info_cache  # noqa: F401


def _lehrkraft() -> JwtPayload:
    return JwtPayload(sub="pseudo-l", roles=["teacher"], grade=None, jti="j", iat=1, exp=9999999999)


def _db():
    db = AsyncMock()
    db.add = MagicMock()

    async def _refresh(obj):
        obj.id = uuid4()

    db.refresh = AsyncMock(side_effect=_refresh)
    db.execute = _make_execute_mock()
    return db


async def _strom(vorliebe) -> tuple[str, dict]:
    http = _FakeHttpClient()
    with patch("app.chat.router.httpx.AsyncClient", return_value=http), \
         patch("app.chat.router.vorliebe_anwenden", AsyncMock(return_value=vorliebe)), \
         patch("app.chat.router.settings") as s:
        s.chat_default_model = "chat-standard"
        s.litellm_verify_ssl = True
        s.title_model = ""
        s.litellm_proxy_url = "http://litellm:4000"
        s.litellm_master_key = "test-key"
        s.upload_max_files = 3
        antwort = await chat(ChatRequest(messages=[{"role": "user", "content": "Hallo"}]),
                             current_user=_lehrkraft(), db=_db())
        teile = [t if isinstance(t, str) else t.decode() async for t in antwort.body_iterator]
    return "".join(teile), http.last_json


@pytest.mark.asyncio
async def test_hinweis_kommt_als_ereignis_mit_dem_tatsaechlichen_modell():
    text, anfrage = await _strom(("chat-standard", "Dein bevorzugtes Modell „x“ ist nicht mehr freigeschaltet — "
                                                   "dieser Chat läuft mit „chat-standard“."))
    assert anfrage["model"] == "chat-standard"
    block = next(b for b in text.split("\n\n") if b.startswith("event: modell_hinweis"))
    daten = json.loads(block.split("data: ", 1)[1])
    assert daten["modell"] == "chat-standard"
    assert "nicht mehr freigeschaltet" in daten["detail"]


@pytest.mark.asyncio
async def test_ohne_hinweis_kein_ereignis():
    text, anfrage = await _strom(("chat-schnell", None))
    assert anfrage["model"] == "chat-schnell"
    assert "event: modell_hinweis" not in text
