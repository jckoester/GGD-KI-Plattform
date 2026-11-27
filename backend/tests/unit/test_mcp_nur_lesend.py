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
4. **Die YAML-Prüfung speichert nie (0.56, BA):** `curriculum_yaml_pruefen` ist der echte Import
   in einem Savepoint (F4 a); jeder Aufruf von `durchlauf` nennt `speichern=False` ausdrücklich.

**`oauth.py` ist ausgenommen (0.55, AX):** Der Autorisierungsserver muss Clients, Codes,
Verbindungen und Token schreiben. Für ihn gilt eine eigene, enge Prüfung: Er schreibt **nur**
diese vier Tabellen und importiert aus `app.*` nur `OAUTH_ERLAUBT`. Die Werkzeuge erreichen
ihn nicht: `werkzeuge.py` darf `app.mcp.oauth` nicht importieren (eigener Test).
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
    # AY Teil 2 (0.63): Absprachen mit anderen Fächern — nur SELECT, Leserecht wie das Curriculum
    # AY Teil 1 (25.11.2026): Querverweise des Bildungsplans — nur SELECT
    ("app.context.querverweise", "querverweise"): "liest Kanten, Knoten, Fächer und Fundstellen",
    ("app.context.querverweise", "ik_ids_im_baum"): "rechnet nur",
    ("app.context.querverweise", "verweise_kompakt"): "rechnet nur",
    ("app.context.curriculum_assistent", "kompetenzen_des_bands"): "liest die Kompetenzen eines Bands",
    ("app.ratelimit.drossel", "pruefe"): "Drossel, zählt im Speicher",
    ("app.mcp", "werkzeuge"): "eigenes Paket",
    ("app.mcp.auth", "SCOPE"): "eigenes Paket",
    ("app.config", "settings"): "Einstellungen lesen (Proxys, JWT-Geheimnis für die OAuth-Anfrage)",
    ("app.core.client_ip", "client_ip"): "Drossel der OAuth-Endpunkte je IP",
    ("app.mcp.oauth", "Provider"): "Autorisierungsserver (AX) — schreibt nur seine Tabellen, eigene Prüfung unten",
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
    # BD Teil B (0.60): Jahresverlaufspläne — nur die Lesefunktionen, siehe MODUL_ATTRIBUTE["vp"]
    ("app.context", "verlaufsplan"): "Modul; aufgerufen werden nur lade, voll, kurz, kompakt, aktuelles_schuljahr",
    ("app.context.curriculum_assistent", "entwurf_lesen"): "Lesefunktion des Assistenten (get_curriculum_draft)",
    ("app.context.curriculum_assistent", "abdeckung_kompakt"): "Lesefunktion (get_curriculum_coverage)",
    ("app.context.curriculum_assistent", "kompetenzen_lesen"): "Lesefunktion (get_bp_competences)",
    ("app.context.curriculum_assistent", "leitperspektiven_lesen"): "Lesefunktion (get_bp_competences typ=lp)",
    ("app.context.curriculum_export", "build_curriculum_export_dict"): "Export als YAML (BA), liest",
    ("app.context.service", "load_curriculum_tree"): "liest den Baum",
    ("app.context.curriculum_yaml", "KeinRecht"): "Ausnahme",
    # Die begründete Ausnahme (0.56, BA, F4 a): Die Prüfung ist der echte Import in einem
    # Savepoint, der ohne `speichern=True` immer verworfen wird — dieselbe Logik wie die Vorschau
    # in der Oberfläche, keine zweite. `test_durchlauf_nur_ohne_speichern` hält den Aufruf fest.
    ("app.context.curriculum_yaml", "durchlauf"): "Import im Savepoint, immer verworfen (speichern=False)",
}

#: Für ganze Module (nach Modulpfad): welche Attribute benutzt werden dürfen — gleich unter
#: welchem Namen das Modul gebunden ist (`import … as …`), und für jeden Zugriff, nicht nur Aufrufe.
MODUL_ATTRIBUTE = {
    "app.auth.tokens": {"pruefe", "PRAEFIX"},
    "app.context.verlaufsplan": {"lade", "voll", "kurz", "kompakt", "alte_titel", "aktuelles_schuljahr",
                                 "TYP", "LESBAR", "SEQUENZ"},
}

_SCHREIBENDE_METHODEN = {"commit", "add", "add_all", "flush", "delete", "merge", "bulk_save_objects",
                         "insert", "update", "execute_many"}
_SCHREIBENDE_PRAEFIXE = ("create_", "update_", "delete_", "apply_", "anlegen", "speichern", "import_")
_SCHREIBENDE_NAMEN = {"pruefe_entwurf_bearbeiten", "operationen_anwenden", "rahmen_setzen", "zuruecknehmen",
                      "curriculum_neu", "curriculum_waehlen", "bezug_setzen", "erzeuge", "widerrufe"}


#: Der Autorisierungsserver — schreibt, aber nur seine Tabellen (siehe unten).
SCHREIBEND = {"oauth.py"}

#: Was `oauth.py` aus `app.*` holen darf.
OAUTH_ERLAUBT = {
    ("app.auth", "tokens"): "pruefe_zeile, ERLAUBTE_ROLLEN, PRAEFIX",
    ("app.db.models", "OAuthClient"): "eigene Tabelle",
    ("app.db.models", "OAuthCode"): "eigene Tabelle",
    ("app.db.models", "OAuthToken"): "eigene Tabelle (als OAuthTokenZeile)",
    ("app.db.models", "PersonalAccessToken"): "Verbindungen (F7)",
    ("app.mcp.auth", "SCOPE"): "eigenes Paket",
    ("app.mcp.auth", "ZugangstokenPruefer"): "Zugangstoken aus AW weiter annehmen",
    ("app.db.session", "AsyncSessionLocal"): "Sitzungsfabrik",
}

#: Die Modelle, die `oauth.py` schreiben darf (Namen wie im Quelltext).
OAUTH_TABELLEN = {"OAuthClient", "OAuthCode", "OAuthTokenZeile", "PersonalAccessToken"}


def _baeume(quellen=None, *, dateien=None):
    if quellen is not None:
        return [("probe.py", ast.parse(q)) for q in quellen]
    return [(p.name, ast.parse(p.read_text())) for p in sorted(PAKET.glob("*.py"))
            if (p.name in dateien if dateien is not None else p.name not in SCHREIBEND)]


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


def _modulnamen(baum) -> dict[str, str]:
    """Lokaler Name → Modulpfad für die Module aus MODUL_ATTRIBUTE (`from app.auth import tokens`,
    `from app.context import verlaufsplan as vp`, `import app.auth.tokens as t`)."""
    namen = {}
    for n in ast.walk(baum):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                if f"{n.module}.{a.name}" in MODUL_ATTRIBUTE:
                    namen[a.asname or a.name] = f"{n.module}.{a.name}"
        elif isinstance(n, ast.Import):
            for a in n.names:
                if a.name in MODUL_ATTRIBUTE and a.asname:
                    namen[a.asname] = a.name
    return namen


def _modulzugriffe(datei, baum):
    """Zugriffe auf ein Modul aus MODUL_ATTRIBUTE außerhalb seiner Liste — auch ohne Aufruf
    (`g = vp.bezugskanten_abgleichen`) und das Modul selbst als Wert (`h = vp`)."""
    namen = _modulnamen(baum)
    if not namen:
        return set()
    basis = {id(n.value) for n in ast.walk(baum) if isinstance(n, ast.Attribute)}
    funde = set()
    for n in ast.walk(baum):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in namen:
            if n.attr not in MODUL_ATTRIBUTE[namen[n.value.id]]:
                funde.add(f"{datei}:{n.lineno} {n.value.id}.{n.attr}")
        elif isinstance(n, ast.Name) and n.id in namen and id(n) not in basis:
            funde.add(f"{datei}:{n.lineno} {n.id} (Modul als Wert)")
    return funde


def _schreibende_aufrufe(baeume):
    funde = set()
    for datei, baum in baeume:
        funde |= _modulzugriffe(datei, baum)
        namen = _modulnamen(baum)
        for n in ast.walk(baum):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in namen:
                continue   # geprüft in _modulzugriffe
            if (isinstance(f, ast.Attribute) and name in _SCHREIBENDE_METHODEN) or name in _SCHREIBENDE_NAMEN \
                    or name.startswith(_SCHREIBENDE_PRAEFIXE):
                funde.add(f"{datei}:{n.lineno} {name}")
    return sorted(funde)


def test_importe_nur_aus_der_liste():
    offen = _unerlaubte_importe(_baeume())
    assert not offen, ("Neuer Import in app/mcp — liest er nur? Dann mit Grund in ERLAUBT "
                       f"eintragen, sonst gehört er nicht in den MCP-Server: {offen}")


def _oauth_ziele(baeume):
    """Modelle, auf die `oauth.py` schreibt: `sa.update/delete/insert(X)` und jede Erzeugung
    eines Modells aus `app.db.models` — eine neue Zeile entsteht nur so (`db.add` bekommt oft
    eine Variable, deren Typ der Baum nicht kennt)."""
    ziele = set()
    for _, baum in baeume:
        modelle = {a.asname or a.name for n in ast.walk(baum)
                   if isinstance(n, ast.ImportFrom) and n.module == "app.db.models" for a in n.names}
        for n in ast.walk(baum):
            if not isinstance(n, ast.Call):
                continue
            if (isinstance(n.func, ast.Attribute) and n.func.attr in {"update", "delete", "insert"}
                    and n.args and isinstance(n.args[0], ast.Name)):
                ziele.add(n.args[0].id)
            elif isinstance(n.func, ast.Name) and n.func.id in modelle:
                ziele.add(n.func.id)
    return ziele


def test_oauth_schreibt_nur_eigene_tabellen():
    baeume = _baeume(dateien=SCHREIBEND)
    assert _oauth_ziele(baeume) <= OAUTH_TABELLEN, _oauth_ziele(baeume) - OAUTH_TABELLEN
    fremd = sorted({f"{d}: from {m} import {n}" for d, m, n in _importe(baeume) if (m, n) not in OAUTH_ERLAUBT})
    assert not fremd, f"Neuer Import im Autorisierungsserver — prüfen und in OAUTH_ERLAUBT eintragen: {fremd}"


def test_gegenprobe_oauth_fremde_tabelle():
    assert _oauth_ziele(_baeume(["async def f(db):\n    await db.execute(sa.update(ContextNode))"])) - OAUTH_TABELLEN
    assert _oauth_ziele(_baeume(["from app.db.models import ContextNode\nasync def f(db):\n    db.add(ContextNode(title='x'))"])) - OAUTH_TABELLEN


def test_werkzeuge_erreichen_den_autorisierungsserver_nicht():
    """`server.py` darf den Provider holen (er hängt ihn ein), die Werkzeuge nicht."""
    importe = {m for d, m, _ in _importe(_baeume(dateien={"werkzeuge.py"}))}
    assert "app.mcp.oauth" not in importe and "app.mcp.server" not in importe


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
    "from app.auth import tokens\nasync def f(db):\n    await tokens.erzeuge(db)",
    # Module aus MODUL_ATTRIBUTE unter jedem Namen, auch ohne Aufruf (Review BD Teil B, 26.11.2026)
    "from app.context import verlaufsplan\nasync def f(db, p):\n    await verlaufsplan.bezugskanten_abgleichen(db, p)",
    "from app.context import verlaufsplan as vp\nasync def f(db, p):\n    g = vp.bezugskanten_abgleichen\n    await g(db, p)",
    "from app.context import verlaufsplan as vp\nasync def f(db, p):\n    h = vp\n    await h.bezugskanten_abgleichen(db, p)",
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


def _durchlauf_aufrufe(baeume):
    """Aufrufe von `durchlauf` und ob sie ausdrücklich `speichern=False` übergeben."""
    for datei, baum in baeume:
        for n in ast.walk(baum):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", "")) == "durchlauf":
                sicher = any(k.arg == "speichern" and isinstance(k.value, ast.Constant) and k.value.value is False
                             for k in n.keywords)
                yield f"{datei}:{n.lineno}", sicher


def test_durchlauf_nur_ohne_speichern():
    """Die YAML-Prüfung (BA) importiert im Savepoint — gespeichert werden darf über MCP nie.
    Jeder Aufruf nennt `speichern=False` ausdrücklich; ein Vorgabewert, der sich ändert, oder eine
    Variable reichen nicht."""
    aufrufe = list(_durchlauf_aufrufe(_baeume()))
    assert aufrufe, "curriculum_yaml_pruefen ruft durchlauf nicht mehr auf — Liste prüfen"
    assert all(sicher for _, sicher in aufrufe), aufrufe


@pytest.mark.parametrize("quelle", [
    "async def f(db, t, u):\n    await durchlauf(db, t, u)",
    "async def f(db, t, u):\n    await durchlauf(db, t, u, speichern=True)",
    "async def f(db, t, u, s):\n    await durchlauf(db, t, u, speichern=s)",
])
def test_gegenprobe_durchlauf(quelle):
    assert not all(sicher for _, sicher in _durchlauf_aufrufe(_baeume([quelle])))
