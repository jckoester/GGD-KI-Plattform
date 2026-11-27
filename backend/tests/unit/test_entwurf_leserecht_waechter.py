"""Wächter: Die Leseregel für Curriculum-Entwürfe bleibt aus schreibenden Wegen (0.52, AZ).

Seit 0.52 lesen alle Lehrkräfte Entwürfe (`darf_entwurf_lesen`), bearbeiten darf sie weiter nur
die Fachschaft (`darf_entwurf_bearbeiten`). Bis dahin regelte eine Prüfung beides; jede
Schreibroute, die zum Lesen eines Knotens die Leseprüfung aufrief, war damit nebenbei auch
gegen Fremde geschützt. Das gilt nicht mehr — gefunden beim Bau dieses Tests: `POST /edges`
hängte ein eigenes Kapitel in einen fremden Entwurf.

Der Test verfolgt statisch (AST, über `app/`), wer die Leseregel direkt oder über Hilfsfunktionen
aufruft. Jede solche Stelle ist entweder eine reine GET-Route, eine bekannte lesende
Hilfsfunktion oder steht in ``ERLAUBT`` — mit Grund und, wo sie etwas ändert, mit der Prüfung,
die danach das Bearbeitungsrecht sicherstellt. Eine neue Stelle schlägt an, bis jemand sie
bewusst einträgt.
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

#: Die Leseregel selbst.
LESEREGEL = {"darf_entwurf_lesen", "pruefe_entwurf_lesen"}

#: Hier endet die Verfolgung: die Bearbeitungsprüfung ruft die Leseprüfung nur, um für
#: Unbefugte bei 404 zu bleiben.
SPERRE = {"pruefe_entwurf_bearbeiten"}

#: Wer die Leseregel **direkt** aufruft. Eine neue Stelle gehört bewusst hierher.
DIREKT = {"_check_read_permission", "_curriculum_lesen", "_lesbare_curricula",
          "pruefe_entwurf_lesen", "pruefe_entwurf_bearbeiten",
          # Übersicht der Leitlinien (0.53, AU): zählt Entwürfe mit, liest nur.
          "leitlinien_fundstellen", "leitlinien_uebersicht",
          # MCP-Server für KI-Abos (0.54, AW): Liste der Curricula, liest nur.
          "lies_curricula",
          # Absprachen zwischen Fächern (0.63, AY Teil 2): Entwürfe anderer Fächer gekennzeichnet, liest nur.
          "absprachen_des_curriculums"}

#: Lesende Hilfsfunktionen ohne eigene Route.
LESEND = {"_check_read_permission", "_curriculum_lesen", "_lesbares_curriculum",
          "_lesbare_curricula", "_entwurfsbaum", "leitlinien_fundstellen", "leitlinien_uebersicht",
          # MCP-Server (0.54, AW): nur lesende Werkzeuge; der Wächter `test_mcp_nur_lesend` hält
          # das Paket von schreibenden Funktionen fern.
          "_curriculum_fuer_werkzeug", "lies_abdeckung", "lies_curricula", "lies_curriculum", "lies_uebersicht",
          # 0.56 (BA): das Curriculum als YAML, wie der Export.
          "lies_curriculum_yaml",
          # 0.63 (AY Teil 2): Absprachen in beide Richtungen.
          "absprachen_des_curriculums"}

#: Nicht lesende Stellen, die die Leseregel benutzen: Grund und die Prüfung, die sie danach
#: aufrufen müssen (``None``: ändert nichts an einem Entwurf).
ERLAUBT = {
    "copy_node": ("kopiert keinen Entwurf — weist ihn mit 422 ab", None),
    "add_chat_context_node": ("heftet nur aktive Bausteine an", None),
    "knoten_beim_anlegen_anheften": ("heftet nur aktive Bausteine an", None),
    "begriffe_im_curriculum_aufloesen": ("POST, gleicht nur Namen ab, ändert nichts", None),
    # AY Teil 1 (25.11.2026): Fundstellen der Querverweise — liest Curricula nur, Entwürfe für
    # Lehrkräfte gekennzeichnet; POST wegen der Länge der ID-Liste.
    "querverweise_lesen": ("POST, liest nur Querverweise und Fundstellen", None),
    "querverweise": ("liest nur (Bildungsplan, Fundstellen)", None),
    "_fundstellen_anhaengen": ("liest nur Fundstellen über `leitlinien_fundstellen`", None),
    "create_edge": ("Kante in einen Entwurf braucht danach das Bearbeitungsrecht",
                    "pruefe_entwurf_bearbeiten"),
    "curriculum_veroeffentlichen": ("veröffentlichen erst nach dem Recht dazu", "darf_veroeffentlichen"),
    "curriculum_als_entwurf_kopieren": ("kopieren erst nach dem Bearbeitungsrecht", "darf_entwurf_bearbeiten"),
}

_METHODEN = {"get", "post", "put", "patch", "delete"}


def _aufrufe(fn) -> set[str]:
    namen = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                namen.add(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                namen.add(n.func.attr)
    return namen


def _methoden(fn) -> set[str]:
    aus = set()
    for d in fn.decorator_list:
        if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in _METHODEN:
            aus.add(d.func.attr)
    return aus


def _funktionen() -> dict[str, tuple[set[str], set[str], str]]:
    """Name → (Aufrufe, HTTP-Methoden, Datei). Namen sind in `app/` für diese Zwecke eindeutig."""
    aus = {}
    for datei in APP.rglob("*.py"):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for n in ast.walk(baum):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                alt = aus.get(n.name)
                aufrufe, methoden = _aufrufe(n), _methoden(n)
                if alt:  # gleichnamige Funktionen: vereinigen, lieber zu viel prüfen
                    aufrufe |= alt[0]
                    methoden |= alt[1]
                aus[n.name] = (aufrufe, methoden, str(datei.relative_to(APP)))
    return aus


def _nutzer_der_leseregel(funktionen) -> set[str]:
    """Alle Funktionen, die die Leseregel direkt oder über andere erreichen — ohne durch die
    Sperre oder schon begründete Stellen hindurchzugehen."""
    erreicht = set(LESEREGEL)
    while True:
        neu = {name for name, (aufrufe, _, _) in funktionen.items()
               if name not in erreicht and aufrufe & (erreicht - SPERRE - set(ERLAUBT))}
        if not neu:
            return erreicht - LESEREGEL
        erreicht |= neu


def test_direkte_aufrufer_der_leseregel():
    funktionen = _funktionen()
    direkt = {name for name, (aufrufe, _, _) in funktionen.items() if aufrufe & LESEREGEL}
    assert direkt == DIREKT, (
        "Neue Stelle ruft die Leseregel für Entwürfe direkt auf — prüfen, ob sie nur liest, "
        f"und in DIREKT eintragen: {sorted(direkt - DIREKT)}; entfallen: {sorted(DIREKT - direkt)}")


def test_keine_schreibende_stelle_ohne_begruendung():
    funktionen = _funktionen()
    offen = []
    for name in sorted(_nutzer_der_leseregel(funktionen) - SPERRE):
        _, methoden, datei = funktionen[name]
        if name in LESEND or name in ERLAUBT or name in DIREKT:
            continue
        if methoden and methoden <= {"get"}:
            continue
        offen.append(f"{datei}:{name} ({', '.join(sorted(methoden)) or 'keine Route'})")
    assert not offen, (
        "Diese Stellen erreichen die Leseregel für Entwürfe, sind aber keine reinen GET-Routen. "
        "Seit 0.52 lesen alle Lehrkräfte Entwürfe — wer etwas ändert, braucht danach "
        f"`pruefe_entwurf_bearbeiten`. Prüfen und in ERLAUBT eintragen: {offen}")


def test_begruendete_stellen_pruefen_danach_das_recht():
    funktionen = _funktionen()
    for name, (grund, pruefung) in ERLAUBT.items():
        assert name in funktionen, f"{name} gibt es nicht mehr — aus ERLAUBT streichen"
        if pruefung:
            assert pruefung in funktionen[name][0], f"{name}: {grund}, ruft aber {pruefung} nicht auf"


def test_gegenprobe_der_waechter_greift():
    """Eine erfundene POST-Route, die die Leseprüfung ruft, muss auffallen."""
    funktionen = _funktionen() | {"neue_route": ({"_check_read_permission"}, {"post"}, "x.py")}
    assert "neue_route" in _nutzer_der_leseregel(funktionen)
