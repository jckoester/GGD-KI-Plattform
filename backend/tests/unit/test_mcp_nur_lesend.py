"""Wächter: Der MCP-Server bleibt lesend (0.54, Päckchen AW Schritt 5, F2).

Über die Schnittstelle erreicht ein KI-Programm die Plattform mit dem Token einer Lehrkraft,
aber ohne deren Blick. Schreiben gehört deshalb nicht hierher, auch nicht „nur ein bisschen“.
Ein Entwurf aus einem KI-Programm kommt über den YAML-Import mit Vorschau (Päckchen BA).

Drei Prüfungen, alle mit Gegenprobe:

1. **Importe nur aus einer Liste (deny-by-default).** Jeder Name, den `app/mcp/` aus `app.*`
   holt, steht in `ERLAUBT`, mit Grund. Ein neuer Import ist damit ab der ersten Zeile rot —
   wer ihn braucht, prüft, ob er nur liest, und trägt ihn ein.
2. **Keine schreibenden Aufrufe** im Paket selbst: `commit`, `add`, `flush`, `delete`,
   `sa.insert/update/delete` und Namen nach dem Muster `create_…`, `update_…`, `apply_…`.
3. **Jedes Werkzeug ist als lesend gekennzeichnet** (`readOnlyHint`, kein `destructiveHint`).
"""
import ast
import asyncio
import pathlib

import pytest

PAKET = pathlib.Path(__file__).resolve().parents[2] / "app" / "mcp"

#: (Modul, Name) → warum das nur liest.
ERLAUBT: dict[tuple[str, str], str] = {
    ("app.auth", "tokens"): "nur tokens.pruefe (siehe MODUL_ATTRIBUTE); schreibt last_used_at, sonst nichts",
    ("app.auth.jwt", "JwtPayload"): "Datentyp",
    ("app.db.session", "AsyncSessionLocal"): "Sitzungsfabrik; das Paket committet nie",
    ("app.db.models", "ContextNode"): "Abfragen; ein ungespeicherter Knoten trägt das Band",
    ("app.db.models", "Subject"): "Abfragen",
    ("app.version", "plattformversion"): "Versionsangabe",
    ("app.ratelimit.drossel", "pruefe"): "Drossel, zählt im Speicher",
    ("app.mcp", "werkzeuge"): "eigenes Paket",
    ("app.mcp.auth", "SCOPE"): "eigenes Paket",
    ("app.mcp.auth", "ZugangstokenPruefer"): "eigenes Paket",
    ("app.mcp.auth", "principal"): "eigenes Paket",
    ("app.auth.vorschau", "eigenes_zaehlt"): "Leseregel für eigene private Knoten",
    ("app.context.curriculum_entwurf", "ENTWURF"): "Konstante",
    ("app.context.curriculum_entwurf", "darf_entwurf_lesen"): "Leseregel",
    ("app.context.grades", "parse_grade_band"): "reine Funktion",
    ("app.context.editions", "aktive_bp_version"): "reine Funktion",
    ("app.context.leitlinien", "alle_leitlinien"): "liest",
    ("app.context.leitlinien_uebersicht", "leitlinien_uebersicht"): "liest (AU)",
    ("app.context.service", "leitperspektive_code"): "reine Funktion",
    ("app.context.service", "normalize_lp_code"): "reine Funktion",
    ("app.context.router", "_lesbares_curriculum"): "Lesecheck der GET-Routen",
    ("app.context.curriculum_assistent", "entwurf_lesen"): "Lesefunktion des Assistenten (get_curriculum_draft)",
    ("app.context.curriculum_assistent", "abdeckung_kompakt"): "Lesefunktion (get_curriculum_coverage)",
    ("app.context.curriculum_assistent", "kompetenzen_lesen"): "Lesefunktion (get_bp_competences)",
    ("app.context.curriculum_assistent", "leitperspektiven_lesen"): "Lesefunktion (get_bp_competences typ=lp)",
}

#: Für ganze Module: welche Attribute benutzt werden dürfen.
MODUL_ATTRIBUTE = {"tokens": {"pruefe", "PRAEFIX"}}

_SCHREIBENDE_METHODEN = {"commit", "add", "add_all", "flush", "delete", "merge", "bulk_save_objects",
                         "insert", "update", "execute_many"}
_SCHREIBENDE_PRAEFIXE = ("create_", "update_", "delete_", "apply_", "anlegen", "speichern", "import_")
_SCHREIBENDE_NAMEN = {"pruefe_entwurf_bearbeiten", "operationen_anwenden", "rahmen_setzen", "zuruecknehmen",
                      "curriculum_neu", "curriculum_waehlen", "bezug_setzen", "erzeuge", "widerrufe"}


def _baeume(quellen=None):
    if quellen is not None:
        return [("probe.py", ast.parse(q)) for q in quellen]
    return [(p.name, ast.parse(p.read_text())) for p in sorted(PAKET.glob("*.py"))]


def _importe(baeume):
    for datei, baum in baeume:
        for n in ast.walk(baum):
            if isinstance(n, ast.ImportFrom) and (n.module or "").split(".")[0] == "app":
                for a in n.names:
                    yield datei, n.module, a.name
            elif isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.split(".")[0] == "app":
                        yield datei, a.name, "*"


def _unerlaubte_importe(baeume):
    return sorted({f"{d}: from {m} import {n}" for d, m, n in _importe(baeume) if (m, n) not in ERLAUBT})


def _schreibende_aufrufe(baeume):
    funde = set()
    for datei, baum in baeume:
        for n in ast.walk(baum):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in MODUL_ATTRIBUTE:
                if name not in MODUL_ATTRIBUTE[f.value.id]:
                    funde.add(f"{datei}:{n.lineno} {f.value.id}.{name}")
                continue
            if (isinstance(f, ast.Attribute) and name in _SCHREIBENDE_METHODEN) or name in _SCHREIBENDE_NAMEN \
                    or name.startswith(_SCHREIBENDE_PRAEFIXE):
                funde.add(f"{datei}:{n.lineno} {name}")
    return sorted(funde)


def test_importe_nur_aus_der_liste():
    offen = _unerlaubte_importe(_baeume())
    assert not offen, ("Neuer Import in app/mcp — liest er nur? Dann mit Grund in ERLAUBT "
                       f"eintragen, sonst gehört er nicht in den MCP-Server: {offen}")


def test_liste_ohne_karteileichen():
    benutzt = {(m, n) for _, m, n in _importe(_baeume())}
    assert set(ERLAUBT) - benutzt == set(), "In ERLAUBT steht, was keiner mehr importiert"


def test_keine_schreibenden_aufrufe():
    funde = _schreibende_aufrufe(_baeume())
    assert not funde, f"Schreibender Aufruf im MCP-Paket: {funde}"


@pytest.mark.parametrize("quelle", [
    "from app.context.curriculum_assistent import operationen_anwenden",
    "from app.context.router import create_node",
])
def test_gegenprobe_import(quelle):
    assert _unerlaubte_importe(_baeume([quelle]))


@pytest.mark.parametrize("quelle", [
    "async def f(db):\n    await db.commit()",
    "async def f(db, n):\n    db.add(n)",
    "async def f(db):\n    await db.execute(sa.update(X))",
    "async def f(db):\n    await apply_curriculum_operations({}, None)",
    "async def f(db):\n    await tokens.erzeuge(db)",
])
def test_gegenprobe_aufruf(quelle):
    assert _schreibende_aufrufe(_baeume([quelle]))


def test_jedes_werkzeug_lesend_gekennzeichnet():
    from fastapi import FastAPI

    from app.mcp.server import einhaengen

    server = einhaengen(FastAPI(), aktiv=True, oeffentliche_url="https://x.test/api/mcp")
    werkzeuge = asyncio.run(server.list_tools())
    assert werkzeuge
    for w in werkzeuge:
        a = w.annotations
        assert a is not None and a.read_only_hint is True and a.destructive_hint is False, w.name
