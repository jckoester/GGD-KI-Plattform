"""Die Plattformversion — aus `backend/VERSION`, der **einzigen** Quelle (0.13, P4).

Das Backend-Image wird mit dem Kontext `./backend` gebaut und enthält die Datei; der
Frontend-Build liest dieselbe Datei (`frontend/vite.config.js`, `frontend/Dockerfile`).
Bis 0.13 stand die Version nur in `frontend/package.json` — dort, wo das Backend sie nicht
erreicht. Zwei Zahlen wären eine, die bei einer Release vergessen wird.

`GET /health` nennt sie; das Obsidian-Plugin schreibt Phasen erst zurück, wenn die
Plattform alt genug ist, sie dabei nicht zu beschädigen.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

#: `backend/VERSION` — in der Entwicklung wie im Container (`/app/VERSION`).
DATEI = Path(__file__).resolve().parents[1] / "VERSION"

#: Was `/health` meldet, wenn die Datei fehlt. Ein Client, der eine Mindestversion
#: verlangt, behandelt das wie eine zu alte Plattform — die sichere Seite.
UNBEKANNT = "unbekannt"


@lru_cache(maxsize=1)
def plattformversion() -> str:
    """Die Version als ``x.y.z`` — oder ``"unbekannt"``.

    ⚠️ Wirft nie: `/health` ist der Healthcheck des Containers. Eine fehlende
    Versionsdatei darf das Backend nicht als „unhealthy" neu starten lassen.
    """
    try:
        return DATEI.read_text(encoding="utf-8").strip() or UNBEKANNT
    except OSError:
        logger.error("Versionsdatei fehlt: %s — /health meldet die Version als unbekannt.", DATEI)
        return UNBEKANNT
