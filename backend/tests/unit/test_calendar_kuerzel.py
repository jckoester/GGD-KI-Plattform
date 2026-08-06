"""UP-8 Schritt 3 — Kürzel-Zuordnung im Profil.

Der Kern ist `test_kuerzel_erreicht_kein_sprachmodell`: Der Schule wurde zugesagt, dass das
Kürzel ausschließlich für den Stundenplan-Abruf verwendet wird und **nie** an ein
Sprachmodell geht. Eine Zusage, die nur auf Sorgfalt beruht, hält beim nächsten Umbau
nicht — hier wird sie strukturell festgehalten.
"""
import ast
import json
from pathlib import Path

import httpx
import pytest

from app.calendar.service import (
    KUERZEL_PREFERENCE_KEY,
    NoCalendarSourceError,
    is_configured,
    validate_kuerzel,
)

APP = Path(__file__).resolve().parents[2] / "app"
FIXTURES = Path(__file__).parent / "fixtures"
PAGECONFIG = json.loads((FIXTURES / "webuntis_pageconfig.json").read_text())
KUERZEL = PAGECONFIG["data"]["elements"][0]["name"]


# ── Der strukturelle Nachweis (Abnahme Schritt 3) ────────────────────────────


def _python_files(*folders: str) -> list[Path]:
    return [
        path
        for folder in folders
        for path in (APP / folder).rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def test_kuerzel_erreicht_kein_sprachmodell():
    """Kein Modul, das Modell-Eingaben erzeugt, nennt das Kürzel.

    Geprüft werden die Bereiche, aus denen etwas an ein Sprachmodell gelangen kann: Chat
    (System-Prompt, Werkzeuge, Nachrichten), Kontextspeicher (Knoten, Embeddings,
    Retrieval), pädagogische Präambeln und Assistenten-Konfiguration.

    Das ist strenger als „das Feld wird nicht gelesen": Selbst der Schlüsselname darf dort
    nicht auftauchen. Wer das Kürzel künftig in einen Prompt aufnehmen will, muss diesen
    Test ändern — und damit die Zusage bewusst brechen statt versehentlich.
    """
    treffer = [
        f"{path.relative_to(APP)}"
        for path in _python_files("chat", "context", "pedagogy")
        if KUERZEL_PREFERENCE_KEY in path.read_text(encoding="utf-8")
    ]
    assert treffer == [], (
        f"Das WebUntis-Kürzel taucht in Modell-nahen Modulen auf: {treffer}. "
        f"Zusage an die Schule: Es geht nie an ein Sprachmodell."
    )


def test_preferences_werden_nur_an_einer_stelle_ausserhalb_gelesen():
    """Absicherung der Aussagekraft des Tests oben.

    `get_preferences` liefert **alle** Einstellungen als Dict — ein Aufruf in einem
    Chat-Modul könnte das Kürzel mitschleifen, ohne es beim Namen zu nennen. Solange es
    außerhalb des Preferences-Moduls nur an bekannten Stellen gelesen wird, greift die
    Namensprüfung. Kommt eine Stelle hinzu, ist zu prüfen, was dort weitergereicht wird.
    """
    leser = {
        str(path.relative_to(APP))
        for path in _python_files(".")
        if not str(path.relative_to(APP)).startswith(("preferences/", "calendar/"))
        and "get_preferences" in path.read_text(encoding="utf-8")
    }
    assert leser == {"context/router.py"}, (
        f"Neue Leser von get_preferences: {leser - {'context/router.py'}}. "
        f"Prüfen, ob dort Einstellungen Richtung Sprachmodell weitergereicht werden."
    )


def test_kuerzel_steht_nicht_im_jwt():
    """Das Kürzel gehört nicht in den Token — der geht an den Browser und in jede Anfrage."""
    jwt_quelle = (APP / "auth" / "jwt.py").read_text(encoding="utf-8")
    assert KUERZEL_PREFERENCE_KEY not in jwt_quelle


# ── Prüfung des eingetragenen Kürzels ────────────────────────────────────────


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/WebUntis/jsonrpc.do":
        return httpx.Response(200, json={"result": {
            "sessionId": "S", "personType": 17, "personId": -1}})
    if request.url.path.endswith("/weekly/pageconfig"):
        return httpx.Response(200, json=PAGECONFIG)
    return httpx.Response(404, text="x")


@pytest.fixture
def keine_quelle(monkeypatch):
    monkeypatch.setattr("app.calendar.service.settings.webuntis_server", "")


@pytest.fixture
def echte_quelle(monkeypatch):
    """Eine erreichbare Stundenplanquelle.

    Gepatcht wird `get_adapter`, nicht `httpx.AsyncClient`: Letzteres wirkt global und
    träfe auch den Aufbau des Testtransports selbst.
    """
    from app.calendar.webuntis import WebUntisAdapter

    monkeypatch.setattr("app.calendar.service.settings.webuntis_server", "ggd.webuntis.com")
    monkeypatch.setattr(
        "app.calendar.service.get_adapter",
        lambda: WebUntisAdapter(
            server="ggd.webuntis.com", user="svc", password="geheim",
            client=httpx.AsyncClient(transport=httpx.MockTransport(_handler)),
        ),
    )


# ── Konfiguriert oder nicht ──────────────────────────────────────────────────


def test_ohne_server_gilt_als_nicht_eingerichtet(keine_quelle):
    """Der Normalfall einer Schule ohne WebUntis — kein Fehler, nur nichts zu tun."""
    assert not is_configured()


def test_mit_server_gilt_als_eingerichtet(monkeypatch):
    monkeypatch.setattr("app.calendar.service.settings.webuntis_server", "x.webuntis.com")
    assert is_configured()


# ── Prüfung des eingetragenen Kürzels ────────────────────────────────────────


@pytest.mark.asyncio
async def test_leeren_geht_immer(keine_quelle):
    """Auch ohne erreichbare Quelle — die Abschaltung darf nie blockiert sein."""
    for wert in ("", "   ", None):
        assert await validate_kuerzel(wert) == ""


@pytest.mark.asyncio
async def test_bekanntes_kuerzel_wird_normalisiert(echte_quelle):
    assert await validate_kuerzel(KUERZEL.lower()) == KUERZEL.upper()


@pytest.mark.asyncio
async def test_unbekanntes_kuerzel_wird_abgelehnt(echte_quelle):
    """Ein Tippfehler soll hier auffallen, nicht als stiller Nicht-Abruf."""
    with pytest.raises(ValueError, match="steht nicht in der Kürzel-Liste"):
        await validate_kuerzel("GIBTSNICHT")


@pytest.mark.asyncio
async def test_setzen_ohne_quelle_schlaegt_fehl(keine_quelle):
    """Fail-closed: Was nicht geprüft werden kann, wird nicht gespeichert."""
    with pytest.raises(NoCalendarSourceError):
        await validate_kuerzel("ABC")


@pytest.mark.asyncio
async def test_nicht_text_wird_abgelehnt(echte_quelle):
    with pytest.raises(ValueError, match="Text"):
        await validate_kuerzel(42)


# ── Datenschutz der Fixtures ─────────────────────────────────────────────────


def test_fixtures_enthalten_keine_klartextnamen():
    """Gilt für **jeden** String in **allen** Fixtures, nicht nur bekannte Felder.

    Der Lauf vom 06.08.2026 hat gezeigt, warum eine Feldliste nicht genügt: `pageconfig`
    liefert den vollen Personendatensatz jeder Lehrkraft, und in `externKey` standen zwei
    Anmeldenamen in Klarform (`vorname.nachname`). Geprüft wird deshalb die Form aller
    Werte — erlaubt sind Platzhalter, Großbuchstaben-Kennungen, Zahlen und Farbcodes.
    """
    import re

    erlaubt = re.compile(r"E\d+|UNTIS_[A-Z]+|[A-Z_]+|\d+|[\d,/]+|#[0-9a-fA-F]{6,8}")
    verdacht: list[str] = []

    def pruefe(node, pfad: str, datei: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                pruefe(value, f"{pfad}.{key}", datei)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                pruefe(value, f"{pfad}[{index}]", datei)
        elif isinstance(node, str) and node and not erlaubt.fullmatch(node):
            verdacht.append(f"{datei}{pfad} = {node[:50]!r}")

    for pfad in sorted(FIXTURES.glob("webuntis_*.json")):
        pruefe(json.loads(pfad.read_text(encoding="utf-8")), "", pfad.name)

    assert verdacht == [], f"Klartext in Fixtures: {verdacht[:5]}"


def test_anonymisierung_deckt_die_personenfelder_ab():
    """Hält fest, welche Felder `pageconfig` liefert und dass sie behandelt werden.

    Ohne diesen Test fiele erst beim nächsten Aufzeichnen auf, dass ein Personenfeld
    hinzugekommen ist.
    """
    quelle = (
        Path(__file__).resolve().parents[3] / "scripts" / "webuntis_probe.py"
    ).read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    label_keys = next(
        {element.value for element in knoten.value.elts}
        for knoten in ast.walk(baum)
        if isinstance(knoten, ast.Assign)
        and getattr(knoten.targets[0], "id", None) == "_LABEL_KEYS"
    )
    assert {"externKey", "forename", "name", "displayname", "longName"} <= label_keys


# ── Navigationssteuerung ─────────────────────────────────────────────────────


def test_status_fragt_die_quelle_nicht(monkeypatch):
    """`is_configured()` darf WebUntis **nicht** kontaktieren.

    Die Antwort steuert Sidebar und Einstellungskachel, wird also bei jedem Seitenaufruf
    gebraucht. Eine Anmeldung samt Elementabruf wäre dafür der falsche Preis — und würde
    das Menü von der Erreichbarkeit eines fremden Servers abhängig machen.
    """
    gerufen = []
    monkeypatch.setattr(
        "app.calendar.service.get_adapter",
        lambda: gerufen.append("adapter"),
    )
    monkeypatch.setattr("app.calendar.service.settings.webuntis_server", "x.webuntis.com")
    assert is_configured()
    assert gerufen == []
