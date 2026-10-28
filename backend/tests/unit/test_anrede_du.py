"""Die Plattform duzt (0.25, Plan „Release 0.25 — Neuigkeiten verdichten, Anrede du").

Wächter gegen Rückfälle in den Texten, die Nutzer:innen lesen: Oberfläche (`frontend/src`
ohne Tests und Kommentare), Hilfe (`docs/user`), Neuigkeiten und die Meldungen des Backends.

Erkannt wird ein großgeschriebenes „Sie“, „Ihnen“ oder „Ihr…“ **mitten im Satz** — dort ist
es immer die Anrede, denn „sie“ in der dritten Person steht klein. Am Satzanfang lässt sich
beides nicht unterscheiden („Sie bleiben erhalten“); dort sieht der Wächter nichts. Eine
Lücke, aber eine kleine: Die meisten Anreden stehen nicht vorn („Möchten Sie …“, „… Ihre
Gruppe“).

Nicht geprüft: `docs/admin` und `docs/dev` (für die Schul-IT, dort bleibt „Sie“) und
Meldungen, die nur im Log der Betreiber:innen landen (`AUSNAHMEN`).
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[3]

ANREDE = re.compile(r"\b(Sie|Ihnen|Ihr|Ihre|Ihren|Ihrem|Ihrer|Ihres)\b(?!-)")  # nicht „Sie-Form"
# Was vor einem Satzanfang stehen darf: Zeilenanfang, Satzzeichen, Aufzählung, Auszeichnung.
SATZANFANG = re.compile(r"""(^|[.!?:;—–]|^\s*([-*>#]+|\d+\.)|[„"'`(\[{>*_|]|\$\{)\s*$""")

# Datei → Teilstrings von Zeilen, die beim „Sie“ bleiben dürfen (mit Grund).
AUSNAHMEN: dict[str, tuple[str, ...]] = {
    # Modul-Docstring: zitiert die Sie-Form als Erkennungsgegenstand, keine Anrede.
    "backend/app/context/operator_erkennung.py": ("Erläutern Sie",),
    # Die drei folgenden sind `logger.warning` beim Start — sie lesen nur Betreiber:innen
    # im Log, keine Oberfläche zeigt sie an.
    "backend/app/core/vorlagenabgleich.py": ("nicht in Ihrer",),
    "backend/app/crisis/config.py": ("übernehmen Sie den Abschnitt", "mit Ihrer Schulsozialarbeit"),
    "backend/app/ui/levels.py": ("keiner Stufe Ihrer", "können Sie die Meldung"),
}


def _treffer(text: str) -> list[tuple[int, str]]:
    funde = []
    for nr, zeile in enumerate(text.splitlines(), 1):
        for m in ANREDE.finditer(zeile):
            if not SATZANFANG.search(zeile[: m.start()]):
                funde.append((nr, zeile.strip()))
                break
    return funde


def _ohne_kommentare(text: str) -> str:
    """Kommentare durch Leerzeilen ersetzen — die Zeilennummern bleiben stimmen."""
    leer = lambda m: "\n" * m.group(0).count("\n")  # noqa: E731
    text = re.sub(r"/\*.*?\*/", leer, text, flags=re.S)
    text = re.sub(r"<!--.*?-->", leer, text, flags=re.S)
    return re.sub(r"(^|\s)//.*$", r"\1", text, flags=re.M)


def _python_texte(text: str) -> str:
    """Nur die Zeichenketten einer Python-Datei, an ihrer Zeile — Kommentare fallen weg."""
    zeilen = [""] * (text.count("\n") + 2)
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.STRING:
            zeilen[tok.start[0] - 1] += " " + tok.string
    return "\n".join(zeilen)


def _quellen():
    for p in sorted((WURZEL / "frontend" / "src").rglob("*")):
        if p.suffix in {".svelte", ".js"} and not p.name.endswith(".test.js"):
            yield p, _ohne_kommentare(p.read_text(encoding="utf-8"))
    for p in sorted((WURZEL / "docs" / "user").glob("*.md")):
        yield p, p.read_text(encoding="utf-8")
    neu = WURZEL / "backend" / "app" / "neuigkeiten" / "neuigkeiten.yaml"
    yield neu, "\n".join(z.split("#")[0] if z.lstrip().startswith("#") else z
                         for z in neu.read_text(encoding="utf-8").splitlines())
    for p in sorted((WURZEL / "backend" / "app").rglob("*.py")):
        yield p, _python_texte(p.read_text(encoding="utf-8"))


def test_erkennt_die_anrede_mitten_im_satz():
    assert _treffer("Möchten Sie das löschen?")
    assert _treffer("Für Ihre Gruppen ist nichts angelegt.")
    assert _treffer("Das zeigt Ihnen die Leiste.")
    assert not _treffer("Sie bleiben beim Speichern erhalten.")      # dritte Person, vorn
    assert not _treffer("Zu dieser Frage: Sie betrifft Chemie.")
    assert not _treffer("- Sie lässt sich teilen.")
    assert not _treffer("Möchtest du das löschen?")
    assert not _treffer("Erkennt auch die Sie-Form.")


def test_die_plattform_duzt():
    funde = []
    for pfad, text in _quellen():
        rel = str(pfad.relative_to(WURZEL))
        erlaubt = AUSNAHMEN.get(rel, ())
        funde += [f"{rel}:{nr}: {z}" for nr, z in _treffer(text)
                  if not any(a in z for a in erlaubt)]
    assert not funde, "Sie-Anrede gefunden — die Plattform duzt (du klein):\n" + "\n".join(funde)
