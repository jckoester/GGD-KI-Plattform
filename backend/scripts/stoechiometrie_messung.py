#!/usr/bin/env python3
"""Messung „Rechenhilfe Stöchiometrie" (Plan `Plaene/Stoechiometrie-Assistent-Plan.md`, Schritt 4).

    python scripts/stoechiometrie_messung.py --selbsttest
    python scripts/stoechiometrie_messung.py --lauf 1 --ziel "<Vault>/Plaene/Messungen-Stoechiometrie"
    python scripts/stoechiometrie_messung.py --lauf 1 --nur A1-loesung-verlangt --nur C3-atom-statt-molekuel

**Was es tut:** Legt den Assistenten „Rechenhilfe Stöchiometrie" an (oder bringt ihn auf den
Stand der Promptdatei — jeder Lauf misst also den Prompt, der im Repo steht), spielt je Fall aus
`scripts/szenarien/stoechiometrie.yaml` eine neue Konversation als Schüler:in mit der Stufe des
Falls durch und schreibt ein Protokoll (Markdown zum Abhaken, JSON zum Vergleichen).

**Automatisch geprüft wird nur der Vorgriff** (Feld `verboten`): Zeichenketten, die die
Schüler:in noch nicht selbst genannt hat. Die `muss`/`darf_nicht`-Kriterien prüft Jan im
Protokoll. Dazu die Formkennzahlen aus `chat_probe.kennzahlen` (Fragezeichen, Wörter, Listen,
Überschriften) und die Sätze.

**Die Normalisierung** (Dateikopf der Szenarien) gilt für Antwort **und** Prüfwert gleich:
`$`, `\\ce{…}`, `\\mathrm{…}`, `\\text{…}` auspacken; `{,}` → `,`; `\\cdot`/`×` → `·` ohne
Leerzeichen daneben; `^{23}` → `^23`; Hoch- und Tiefstellzahlen → Ziffern; Pfeile → `->`;
`/` ohne Leerzeichen daneben; schmale und geschützte Leerzeichen → Leerzeichen; Dezimalpunkt
zwischen Ziffern → Komma. **Zahlen an Ziffergrenzen**: „0,2" trifft nicht in „0,25" und nicht
in „10,2". Vor dem ersten Lauf prüft `--selbsttest` das Instrument in beide Richtungen.

**Eigene Daten:** Der Assistent bleibt bestehen (Name ist der Schlüssel). Die Konversationen
des Laufs werden am Ende gelöscht — ihr Inhalt steht im Protokoll.

**Dazu, nach dem Lauf** (seit Lauf 4, 24.10.2026):
`assistent_systemtext.py <verlauf.json> <fall> <konto>` baut den Systemtext eines Zugs nach und legt ihn
ins JSON; `stoechiometrie_zusatz.py <verlauf.json> <verlauf.md> [Kopfzeile …]` hängt Frageform, fremde
Zahlen (D1/D4/D5) und den E1-Verlauf an das Protokoll an.

⚠️ Nur für Entwicklungsinstanzen — eigene Sitzungs-Token, echte Modellaufrufe auf Kosten des
Budgets des Schüler:innen-Kontos.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth.dependencies import get_jwt_service
from app.config import settings

HIER = Path(__file__).resolve().parent
REPO = HIER.parent.parent
PROMPT = REPO / "config/prompts/stoechiometrie_assistent.md"
SZENARIEN = HIER / "szenarien/stoechiometrie.yaml"
NAME = "Rechenhilfe Stöchiometrie"
#: Einrichtung v3 (Plan, 23.10.2026): alle Lernverhalten-Augmentierungen an außer den
#: Reflexions-Hinweisen — sie erzeugen „Möchtest du noch …?"-Anhängsel.
EINRICHTUNG_OHNE = ["metacognitive_nudges"]
#: Festes Modell des Assistenten (Jan, 24.10.2026, nach Lauf 3): chat-komplex.
EINRICHTUNG_MODELL = "chat-komplex"


def _lade(name: str):
    """`scripts/` ist kein Paket (CLAUDE.md, „scripts/-Paketkonflikt") — über den Pfad laden."""
    spec = importlib.util.spec_from_file_location(name, HIER / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


chat_probe = _lade("chat_probe")
entfall = _lade("entfall_messung")
_alle, _eins = entfall._alle, entfall._eins


# ── Vorgriff-Prüfung ─────────────────────────────────────────────────────────

_HOCH = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
_TIEF = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_HOCHZAHL = re.compile(r"([⁰¹²³⁴⁵⁶⁷⁸⁹]+)")


def normalisieren(text: str) -> str:
    t = text or ""
    t = _HOCHZAHL.sub(lambda m: "^" + m.group(1).translate(_HOCH), t)
    t = t.translate(_TIEF)
    for befehl in ("ce", "mathrm", "text", "mathit", "operatorname"):
        # Geschachtelte Klammern kommen in diesen Befehlen praktisch nicht vor ({,} ausgenommen).
        t = re.sub(r"\\" + befehl + r"\s*\{((?:[^{}]|\{,\})*)\}", r"\1", t)
    t = t.replace("{,}", ",").replace("$", "")
    t = re.sub(r"\\[()\[\]]", " ", t)          # \( \) \[ \] — Begrenzer wie $
    t = re.sub(r"\\[dt]frac", r"\\frac", t)
    t = re.sub(r"\\[,;: ]|\\quad|\\!", " ", t)
    t = t.replace("\\%", "%")
    t = re.sub(r"\\cdot|\\times|×|⋅", "·", t)
    t = re.sub(r"\\rightarrow|\\longrightarrow|\\to\b|→|⟶|⇒", "->", t)
    t = re.sub(r"\^\{([^{}]*)\}", r"^\1", t)
    t = re.sub(r"[    ]", " ", t)
    t = re.sub(r"(?<=\d)\.(?=\d)", ",", t)
    t = re.sub(r"\s*·\s*", "·", t)
    t = re.sub(r"\s*/\s*", "/", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _muster(verboten: str) -> re.Pattern:
    v = normalisieren(verboten).strip()
    vorn = r"(?<![\d,])" if v[:1].isdigit() else (r"(?<![\w])" if v[:1].isalpha() else "")
    hinten = r"(?!\d|,\d)" if v[-1:].isdigit() else ""
    flags = re.IGNORECASE if re.fullmatch(r"[A-Za-zÄÖÜäöüß ]+", v) else 0
    return re.compile(vorn + re.escape(v) + hinten, flags)


_SATZGRENZE = re.compile(r"(?<=[.!?:])\s+(?=[A-ZÄÖÜ„$\\(])|\n+")


def vorgriffe(antwort: str, verboten: list[str]) -> list[dict]:
    """Treffer je verbotenem Wert — mit dem Satz, in dem er steht (normalisiert)."""
    saetze = [normalisieren(s).strip() for s in _SATZGRENZE.split(antwort or "") if s.strip()]
    treffer = []
    for v in verboten or []:
        m = _muster(v)
        fund = [s for s in saetze if m.search(s)]
        if fund:
            treffer.append({"wert": v, "saetze": fund})
    return treffer


def saetze_zaehlen(antwort: str) -> int:
    rein = re.sub(r"\$[^$]*\$", "X", antwort or "")
    return len([s for s in re.split(r"(?<=[.!?])\s+|\n+", rein) if re.search(r"\w", s)])


def _als_latex(v: str) -> str:
    if re.search(r"[A-Z][a-z]?\d|[A-Z][a-z]? [+]|^\d+ [A-Z]", v):
        return f"Also $\\ce{{{v.replace('->', '->')}}}$ ist es."
    latex = v.replace(",", "{,}").replace("·", "\\cdot ").replace("%", "\\%").replace(" mol", "\\,\\mathrm{mol}")
    return f"Damit ist es ${latex}$."


def _gegenprobe(v: str) -> str:
    if v[-1:].isdigit():
        return f"Es sind {v}5 und nicht mehr."
    if v[:1].isdigit():
        return f"Es sind 1{v} gewesen."
    if "/" in v:
        return "Rechne M/m und vergleiche."
    if v.startswith("\\frac"):
        return "Nimm $\\frac{M}{m}$ als Ansatz."
    return "Das ist halb so viel."


def selbsttest(faelle: list[dict]) -> bool:
    """Je Fall ein Satz, der treffen muss (LaTeX-Schreibweise des ersten verbotenen Werts), und
    einer, der nicht treffen darf (benachbarte Zahl). Dazu feste Fälle aus dem Dateikopf."""
    ok = True
    print("Selbsttest der Vorgriff-Prüfung\n")
    fest = [
        ("$0{,}200\\,\\mathrm{mol}$ Magnesium", "0,200 mol", True),
        ("Das sind 0,25 mol.", "0,2 mol", False),
        ("n = 0,25 mol", "0,2", False),
        ("Es sind 10,2 g.", "0,2", False),
        ("$\\ce{2 Mg + O2 -> 2 MgO}$", "2 Mg + O2", True),
        ("$\\ce{Mg + O2 -> MgO}$", "2 Mg", False),
        ("$N = 1{,}5 \\cdot 10^{23}$", "1,5·10", True),
        ("3 · 10²³ Teilchen", "3·10^23", True),
        ("$n = \\frac{m}{M}$", "m/M", False),
        ("$n = \\frac{m}{M}$", "\\frac{m}{M}", True),
        ("n = m / M", "m/M", True),
        ("M(O₂) = 32,0 g/mol", "32,0 g/mol", True),
        ("Die Masse ist doppelt so groß.", "doppelt", True),
        ("Ein Massenanteil von 10\\,\\% ", "10 %", True),
        ("(Tipp: \\(\\ce{2 Mg + O2 -> 2 MgO}\\)).", "2 MgO", True),
        ("\\[ n = \\dfrac{m}{M} \\]", "\\frac{m}{M}", True),
    ]
    for satz, wert, soll in fest:
        ist = bool(vorgriffe(satz, [wert]))
        ok &= ist == soll
        print(f"  {'✓' if ist == soll else '✗'} {'trifft' if soll else 'trifft nicht'}: {wert!r} in {satz!r}")
    print()
    for fall in faelle:
        werte = [v for z in fall["zuege"] for v in (z.get("verboten") or [])]
        if not werte:
            continue
        v = werte[0]
        pos, neg = _als_latex(v), _gegenprobe(v)
        p, n = bool(vorgriffe(pos, [v])), bool(vorgriffe(neg, [v]))
        ok &= p and not n
        print(f"  {'✓' if p and not n else '✗'} {fall['id']:<40} {v!r}: trifft {pos!r} {'ja' if p else 'NEIN'}"
              f" · nicht {neg!r} {'nein' if not n else 'DOCH'}")
    print("\nSelbsttest", "bestanden" if ok else "GESCHEITERT")
    return ok


# ── Einrichtung ──────────────────────────────────────────────────────────────


def assistent(conn, prompt_datei: Path = PROMPT, ohne: list[str] | None = None) -> int:
    """Rechenhilfe Stöchiometrie nach der Tabelle „Einrichtung" im Plan — angelegt oder auf den
    Stand der Promptdatei gebracht.

    Für Experimente in Schritt 5: ``prompt_datei`` (eine Variante außerhalb des Repos) und
    ``ohne`` (abgeschaltete Lernverhalten-Augmentierungen). Ohne beides: die Einrichtung des
    Plans. Der nächste Lauf ohne Optionen stellt sie wieder her."""
    prompt = prompt_datei.read_text(encoding="utf-8").strip()
    ohne = EINRICHTUNG_OHNE if ohne is None else ohne
    chemie = _eins(conn, "SELECT id FROM subjects WHERE slug = 'chemie'")
    werte = dict(system_prompt=prompt, subject_id=chemie, audience="student", scope="all_students",
                 status="active", min_grade=8, max_grade=13, model=EINRICHTUNG_MODELL, tool_groups="[]",
                 disabled_augmentations="{" + ",".join(ohne) + "}")
    kennung = _eins(conn, "SELECT id FROM assistants WHERE name = %s", NAME)
    with conn.cursor() as cur:
        if kennung is None:
            cur.execute(
                "INSERT INTO assistants (name, description, system_prompt, subject_id, audience, scope, status, "
                "min_grade, max_grade, model, tool_groups, disabled_augmentations, visibility, tags, "
                "created_by, creator_role, created_at, updated_at) VALUES "
                "(%(name)s, %(beschreibung)s, %(system_prompt)s, %(subject_id)s, %(audience)s, %(scope)s, "
                "%(status)s, %(min_grade)s, %(max_grade)s, %(model)s, %(tool_groups)s::jsonb, "
                "%(disabled_augmentations)s::text[], 'public', '{}'::text[], '__messung__', 'admin', now(), now()) "
                "RETURNING id",
                werte | {"name": NAME, "beschreibung": "Begleitet stöchiometrische Rechnungen Schritt für Schritt."},
            )
            kennung = cur.fetchone()[0]
        else:
            cur.execute(
                "UPDATE assistants SET system_prompt = %(system_prompt)s, subject_id = %(subject_id)s, "
                "audience = %(audience)s, scope = %(scope)s, status = %(status)s, min_grade = %(min_grade)s, "
                "max_grade = %(max_grade)s, model = %(model)s, tool_groups = %(tool_groups)s::jsonb, "
                "disabled_augmentations = %(disabled_augmentations)s::text[], updated_at = now() WHERE id = %(id)s",
                werte | {"id": kennung},
            )
    # Anker leeren: „Wissensbereich leer" (Plan, Einrichtung).
    with conn.cursor() as cur:
        cur.execute("DELETE FROM assistant_context_anchors WHERE assistant_id = %s", (kennung,))
    return kennung


def prompt_stand(prompt_datei: Path = PROMPT) -> str:
    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout.strip()
    if prompt_datei.resolve() != PROMPT:
        basis = git("log", "-1", "--format=%h", "--", str(PROMPT.relative_to(REPO)))
        return f"**Variante** `{prompt_datei.name}` (nicht im Repo; Basis {basis})"
    rel = str(PROMPT.relative_to(REPO))
    status = git("status", "--porcelain", "--", rel)
    if status.startswith("??"):
        return "unversioniert (noch nicht im Repo)"
    hash_ = git("log", "-1", "--format=%h %cs", "--", rel)
    if not status:
        return hash_
    inhalt = hashlib.sha256(PROMPT.read_bytes()).hexdigest()[:10]
    return f"{hash_} + uncommittete Änderungen (Inhalt sha256 `{inhalt}`)"


def knoten_der_antwort(conn, konversation: str) -> list[str]:
    """Bausteine der **letzten** Antwort (Vorab und Werkzeug) — `Titel (Herkunft)`."""
    return [f"{t} ({h})" for t, h in _alle(
        conn, "SELECT n.title, m.herkunft FROM message_context_nodes m "
              "JOIN context_nodes n ON n.id = m.node_id WHERE m.message_id = ("
              "SELECT id FROM messages WHERE conversation_id = %s AND role = 'assistant' "
              "ORDER BY created_at DESC LIMIT 1) ORDER BY m.position", konversation)]


# ── Lauf ─────────────────────────────────────────────────────────────────────


def fall_durchspielen(conn, jwt, schueler: str, kennung: int, fall: dict, basis: str,
                      modell: str | None = None) -> dict:
    token = jwt.issue(pseudonym=schueler, roles=["student"], grade=str(fall["stufe"]))[0]
    zuege, verlauf, konversation = [], [], None
    with httpx.Client(base_url=basis, timeout=300.0, headers={"Cookie": f"session={token}"}) as client:
        for nr, zug in enumerate(fall["zuege"], start=1):
            try:
                ergebnis = chat_probe.frage_stellen(client, zug["schueler"], assistent=kennung, gruppe=None,
                                                    verlauf=verlauf, konversation=konversation, modell=modell)
            except (httpx.HTTPError, SystemExit) as fehler:
                zuege.append({"nr": nr, "schueler": zug["schueler"], "abbruch": f"{type(fehler).__name__}: {fehler}"})
                break
            konversation = ergebnis["konversation"]
            verlauf += [{"role": "user", "content": zug["schueler"]},
                        {"role": "assistant", "content": ergebnis["antwort"]}]
            zuege.append({
                "nr": nr, "schueler": zug["schueler"], "antwort": ergebnis["antwort"],
                "modell": ergebnis["modell"], "fehler": ergebnis["fehler"],
                "werkzeuge": [w.get("tool") for w in ergebnis["werkzeuge"] if w.get("tool")],
                "angebot": [a["titel"] for a in (ergebnis.get("vorab_debug") or {}).get("angebot", [])],
                "suchanfragen": (ergebnis.get("vorab_debug") or {}).get("suchanfragen", []),
                "knoten": knoten_der_antwort(conn, konversation),
                "vorgriffe": vorgriffe(ergebnis["antwort"], zug.get("verboten")),
                "saetze": saetze_zaehlen(ergebnis["antwort"]),
                **{k: ergebnis[k] for k in ("woerter", "fragezeichen", "ueberschriften", "listenpunkte")},
                "muss": zug.get("muss") or [], "darf_nicht": zug.get("darf_nicht") or [],
            })
            print(f"  {fall['id']} Zug {nr}: {ergebnis['woerter']} Wörter, {ergebnis['fragezeichen']}× ?"
                  f"{'  ⚠️ VORGRIFF ' + ', '.join(t['wert'] for t in zuege[-1]['vorgriffe']) if zuege[-1]['vorgriffe'] else ''}",
                  flush=True)
    return {"id": fall["id"], "titel": fall["titel"], "stufe": fall["stufe"], "referenz": fall.get("referenz"),
            "konversation": konversation, "zuege": zuege}


# ── Protokoll ────────────────────────────────────────────────────────────────


def _zitat(text: str) -> str:
    return "\n".join(f"> {z}" if z else ">" for z in (text or "*(leer)*").splitlines())


def protokoll(kopf: dict, faelle: list[dict]) -> str:
    t = [f"# Rechenhilfe Stöchiometrie — Lauf {kopf['lauf']}", "",
         f"- **Datum:** {kopf['datum']}", f"- **Modell:** {kopf['modell']}",
         f"- **Assistent:** „{NAME}“, ID {kopf['assistent']} (Chemie, Schüler:innen, Kl. 8–13, ohne Wissensbereich, "
         "ohne Fähigkeiten, " + (f"**Augmentierungen aus: {', '.join(kopf['ohne'])}**)" if kopf.get("ohne")
                                  else "alle Lernverhalten-Augmentierungen an)"),
         f"- **Prompt-Stand:** `config/prompts/stoechiometrie_assistent.md` {kopf['prompt']}",
         f"- **Importstand:** {kopf['import']}",
         "- **Schüler:innen-Konto:** Dev-Konto ohne Unterrichtsgruppe, Stufe je Fall im Token; Chat über den "
         "Assistenten (Fach Chemie aus dem Assistenten)",
         "", "Automatisch: **Vorgriff** (verbotene Werte, normalisiert; Treffer mit Satz), Fragezeichen (Soll ≤ 1), "
         "Sätze, Wörter, Listenpunkte, Überschriften. Die Kriterien darunter prüft Jan.", ""]
    for f in faelle:
        t += ["---", "", f"## {f['id']} — {f['titel']} (Kl. {f['stufe']})", "",
              f"*Referenz:* {f['referenz'] or '—'}", ""]
        for z in f["zuege"]:
            t += [f"### Zug {z['nr']}", "", f"**Schüler:in:** {z['schueler']}", ""]
            if "abbruch" in z:
                t += [f"⚠️ abgebrochen — {z['abbruch']}", ""]
                continue
            t += [_zitat(z["antwort"]), ""]
            befund = [f"{z['fragezeichen']}× ?{' ⚠️' if z['fragezeichen'] > 1 else ''}", f"{z['saetze']} Sätze",
                      f"{z['woerter']} Wörter", f"{z['listenpunkte']} Listenpunkte", f"{z['ueberschriften']} Überschriften"]
            t.append("- **Befund:** " + " · ".join(befund))
            if z["vorgriffe"]:
                for v in z["vorgriffe"]:
                    t.append(f"- ⚠️ **Vorgriff „{v['wert']}“:** " + " · ".join(f"„{s}“" for s in v["saetze"]))
            else:
                t.append("- **Vorgriff:** keiner")
            t.append(f"- **Werkzeuge:** {', '.join(z['werkzeuge']) or '—'}"
                     + (f" (Suche: {'; '.join(z['suchanfragen'])})" if z["suchanfragen"] else ""))
            t.append(f"- **Angeboten:** {', '.join(z['angebot']) or '—'} · **Eingesetzt:** {', '.join(z['knoten']) or '—'}")
            if z.get("fehler"):
                t.append(f"- ⚠️ **Fehler im Strom:** {z['fehler']}")
            t.append("")
            if z["muss"] or z["darf_nicht"]:
                t += [f"- [ ] muss: {k}" for k in z["muss"]] + [f"- [ ] darf nicht: {k}" for k in z["darf_nicht"]]
                t.append("- [ ] Zug passt nicht (Assistent hatte etwas anderes gefragt)")
                t.append("")
    t += ["---", "", "## Zusammenfassung (automatisch, ohne Bewertung der Kriterien)", ""]
    zuege = [(f["id"], z) for f in faelle for z in f["zuege"] if "antwort" in z]
    mit_vorgriff = [(i, z) for i, z in zuege if z["vorgriffe"]]
    t.append(f"- **Züge:** {len(zuege)} beantwortet, {sum(1 for f in faelle for z in f['zuege'] if 'abbruch' in z)} abgebrochen")
    t.append(f"- **Vorgriffe:** {len(mit_vorgriff)} Züge"
             + ("" if not mit_vorgriff else " — " + "; ".join(
                 f"{i} Zug {z['nr']}: {', '.join(v['wert'] for v in z['vorgriffe'])}" for i, z in mit_vorgriff)))
    mehr = [(i, z) for i, z in zuege if z["fragezeichen"] > 1]
    t.append(f"- **Mehr als ein Fragezeichen:** {len(mehr)} Züge"
             + ("" if not mehr else " — " + "; ".join(f"{i} Zug {z['nr']} ({z['fragezeichen']})" for i, z in mehr)))
    woerter = sorted(z["woerter"] for _, z in zuege)
    if woerter:
        median = woerter[len(woerter) // 2]
        lang = [(i, z) for i, z in zuege if z["woerter"] > 2 * median and z["woerter"] > 120]
        t.append(f"- **Länge:** Median {median} Wörter, längste {woerter[-1]}"
                 + ("" if not lang else " — auffällig lang (> 2× Median): " + "; ".join(
                     f"{i} Zug {z['nr']} ({z['woerter']})" for i, z in lang)))
    listen = [(i, z) for i, z in zuege if z["listenpunkte"] or z["ueberschriften"]]
    t.append(f"- **Mit Liste oder Überschrift:** {len(listen)} Züge"
             + ("" if not listen else " — " + "; ".join(f"{i} Zug {z['nr']}" for i, z in listen)))
    werkzeug = [(i, z) for i, z in zuege if z["werkzeuge"]]
    t.append(f"- **Mit Werkzeugaufruf:** {len(werkzeug)} Züge")
    return "\n".join(t) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description="Messung Rechenhilfe Stöchiometrie")
    p.add_argument("--selbsttest", action="store_true", help="nur das Prüfinstrument testen")
    p.add_argument("--lauf", default="1", help="Bezeichnung des Laufs (Dateiname verlauf-<lauf>)")
    p.add_argument("--ziel", type=Path, default=None, help="Ordner für verlauf-<n>.md und verlauf-<n>.json")
    p.add_argument("--nur", action="append", default=[], help="nur diesen Fall (mehrfach möglich)")
    p.add_argument("--basis", default="http://localhost:8000")
    p.add_argument("--konto", default=None, help="Pseudonym-Anfang des Schüler:innen-Kontos")
    p.add_argument("--importstand", default="nicht angegeben")
    p.add_argument("--behalten", action="store_true", help="Konversationen nicht löschen")
    p.add_argument("--modell", default=None,
                   help="Modell-Alias je Anfrage (z. B. chat-komplex); ohne = Modell des Assistenten bzw. Standard")
    p.add_argument("--prompt", type=Path, default=PROMPT, help="Promptvariante (Experiment, Schritt 5)")
    p.add_argument("--ohne-augmentierung", action="append", default=None, dest="ohne",
                   help="abgeschaltete Lernverhalten-Augmentierungen statt der Einrichtung "
                        f"({', '.join(EINRICHTUNG_OHNE)}); mehrfach möglich, „keine“ = alle an")
    args = p.parse_args()

    faelle = yaml.safe_load(SZENARIEN.read_text(encoding="utf-8"))["faelle"]
    if not selbsttest(faelle):
        raise SystemExit(1)
    if args.selbsttest:
        return
    if settings.environment == "production":
        p.error("Nicht auf einer Produktivinstanz (eigene Token, echtes Budget).")
    if args.nur:
        faelle = [f for f in faelle if f["id"] in args.nur]

    conn = entfall.verbindung()
    if args.ohne is not None:
        args.ohne = [o for o in args.ohne if o != "keine"]
    kennung = assistent(conn, args.prompt, args.ohne)
    args.ohne = EINRICHTUNG_OHNE if args.ohne is None else args.ohne
    zeile = _alle(conn, "SELECT pseudonym FROM pseudonym_audit WHERE roles::text LIKE '%%student%%' "
                        "AND litellm_key IS NOT NULL AND pseudonym LIKE %s ORDER BY created_at LIMIT 1",
                  (args.konto or "") + "%")
    if not zeile:
        raise SystemExit("Kein Schüler:innen-Konto mit LiteLLM-Schlüssel gefunden.")
    schueler = zeile[0][0]
    jwt = get_jwt_service()
    print(f"\nAssistent {kennung}, Prompt {prompt_stand(args.prompt)}, ohne {args.ohne or '—'}, {len(faelle)} Fälle\n")

    ergebnisse = []
    try:
        for fall in faelle:
            ergebnisse.append(fall_durchspielen(conn, jwt, schueler, kennung, fall, args.basis, args.modell))
    finally:
        if not args.behalten:
            with conn.cursor() as cur:
                for f in ergebnisse:
                    if f["konversation"]:
                        cur.execute("DELETE FROM conversations WHERE id = %s AND pseudonym = %s",
                                    (f["konversation"], schueler))
        conn.close()

    modelle = sorted({z["modell"] for f in ergebnisse for z in f["zuege"] if z.get("modell")})
    kopf = {"lauf": args.lauf, "datum": datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y, %H:%M"),
            "modell": ", ".join(modelle) or "?", "assistent": kennung, "prompt": prompt_stand(args.prompt), "ohne": args.ohne,
            "import": args.importstand}
    text = protokoll(kopf, ergebnisse)
    if args.ziel:
        args.ziel.mkdir(parents=True, exist_ok=True)
        (args.ziel / f"verlauf-{args.lauf}.md").write_text(text, encoding="utf-8")
        (args.ziel / f"verlauf-{args.lauf}.json").write_text(
            json.dumps({"kopf": kopf, "faelle": ergebnisse}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nProtokoll: {args.ziel / f'verlauf-{args.lauf}.md'}")
    else:
        print(text)


if __name__ == "__main__":
    main()
