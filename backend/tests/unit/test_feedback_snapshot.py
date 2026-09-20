"""Die Form des Chat-Anhangs (ADR-020, AP2).

Ohne Datenbank: `baue` rechnet auf gewöhnlichen Objekten. Geprüft wird, was im JSONB
landet — und vor allem, was **nicht**.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from app.feedback import snapshot


def _konversation():
    return SimpleNamespace(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        assistant_id=7,
        model_used="chat-standard",
        title="Bruchrechnen",
    )


def _nachricht(rolle, inhalt, minute):
    return SimpleNamespace(
        role=rolle,
        content=inhalt,
        model="chat-standard" if rolle == "assistant" else None,
        created_at=datetime(2026, 9, 20, 10, minute, tzinfo=timezone.utc),
        # Felder, die es am Modell gibt und die nicht mitkommen sollen:
        cost_usd=0.0021,
        tokens_input=120,
        tokens_output=340,
    )


def test_kopf_traegt_assistent_und_modell():
    ergebnis = snapshot.baue(_konversation(), [])
    assert ergebnis["conversation_id"] == "11111111-1111-1111-1111-111111111111"
    assert ergebnis["assistant_id"] == 7
    assert ergebnis["model_used"] == "chat-standard"
    assert ergebnis["title"] == "Bruchrechnen"
    assert ergebnis["messages"] == []


def test_nachrichten_behalten_ihre_reihenfolge():
    nachrichten = [_nachricht("user", "Frage", 0), _nachricht("assistant", "Antwort", 1)]
    inhalte = [n["content"] for n in snapshot.baue(_konversation(), nachrichten)["messages"]]
    assert inhalte == ["Frage", "Antwort"]


def test_zeitstempel_als_zeichenkette():
    """JSONB kennt kein `datetime` — ohne `isoformat` scheitert erst der Insert."""
    eintrag = snapshot.baue(_konversation(), [_nachricht("user", "Frage", 0)])["messages"][0]
    assert eintrag["created_at"] == "2026-09-20T10:00:00+00:00"


def test_keine_kosten_und_keine_token():
    """Sie beantworten keine Frage, die eine Fehlermeldung stellt."""
    eintrag = snapshot.baue(_konversation(), [_nachricht("assistant", "Antwort", 1)])["messages"][0]
    assert set(eintrag) == {"role", "content", "model", "created_at"}
