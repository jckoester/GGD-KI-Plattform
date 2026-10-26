#!/usr/bin/env python3
"""Messung eines Schüler-Assistenten mit festen Szenarien (Muster: Rechenhilfe Stöchiometrie).

    python scripts/assistent_messung.py --szenarien scripts/szenarien/reaktionsgleichung.yaml --selbsttest
    python scripts/assistent_messung.py --szenarien scripts/szenarien/reaktionsgleichung.yaml \
        --lauf 1 --ziel "<Vault>/Plaene/Messungen-Reaktionsgleichung"

**Der Assistent steht im Kopf der Szenariodatei** (`assistent:` — Name, Beschreibung, Prompt,
Klassenstufen, Modell, abgeschaltete Augmentierungen). Das Skript legt ihn an oder bringt ihn auf den
Stand der Promptdatei; jeder Lauf misst also den Prompt, der im Repo steht. Je Fall spielt es eine
neue Konversation als Schüler:in mit der Stufe des Falls durch und schreibt ein Protokoll (Markdown
zum Abhaken, JSON zum Vergleichen).

**Automatisch geprüft:**
- **Vorgriff** (Feld `verboten` je Zug): Zeichenketten, die die Schüler:in noch nicht selbst
  genannt hat.
- **Stufenvorgriff** (Feld `stufenfremd` je Fall, seit 26.10.2026): Begriffe, die in dieser Stufe
  noch nicht dran sind, etwa „Elektron“ in Klasse 8. Ein Wort trifft auch seine Zusammensetzungen
  („Elektronenabgabe“).
- **Kosten** (seit 26.10.2026): Eingabe- und Ausgabetokens und Kosten je Zug aus `messages`; dazu
  der geschätzte Anteil des Assistenten-Prompts an den Eingabetokens (tiktoken `o200k_base`).
  Er zeigt, ob ein kürzerer Prompt, etwa durch Aufteilen in mehrere Assistenten, nennenswert spart.

Die `muss`/`darf_nicht`-Kriterien prüft Jan im Protokoll. Dazu die Formkennzahlen aus
`chat_probe.kennzahlen` (Fragezeichen, Wörter, Listen, Überschriften) und die Sätze.

**Die Normalisierung** gilt für Antwort **und** Prüfwert gleich:
`$`, `\\ce{…}`, `\\mathrm{…}`, `\\text{…}` auspacken; `{,}` → `,`; `\\cdot`/`×` → `·` ohne
Leerzeichen daneben; `^{23}` → `^23`; Hoch- und Tiefstellzahlen → Ziffern; Pfeile → `->`;
`/` ohne Leerzeichen daneben; schmale und geschützte Leerzeichen → Leerzeichen; Dezimalpunkt
zwischen Ziffern → Komma. **Zahlen an Ziffergrenzen**: „0,2" trifft nicht in „0,25" und nicht
in „10,2". Vor jedem Lauf prüft der Selbsttest das Instrument in beide Richtungen.

**Eigene Daten:** Der Assistent bleibt bestehen (Name ist der Schlüssel). Die Konversationen
des Laufs werden am Ende gelöscht — ihr Inhalt steht im Protokoll.

**Dazu, nach dem Lauf:** `assistent_systemtext.py <verlauf.json> <fall> <konto>` baut den Systemtext
eines Zugs nach und legt ihn ins JSON.

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

#: Vorgaben, wenn der Kopf der Szenariodatei nichts sagt — die Einrichtung der Rechenhilfe
#: (Plan, 23./24.10.2026): Reflexions-Hinweise aus (sie erzeugen „Möchtest du noch …?"-Anhängsel),
#: festes Modell chat-komplex.
VORGABE_OHNE = ["metacognitive_nudges"]
VORGABE_MODELL = "chat-komplex"


def profil_laden(szenarien: Path) -> tuple[dict, list[dict]]:
    """Kopf (`assistent:`) und Fälle einer Szenariodatei. Der Prompt-Pfad ist repo-relativ."""
    daten = yaml.safe_load(szenarien.read_text(encoding="utf-8"))
    kopf = daten.get("assistent") or {}
    for feld in ("name", "prompt"):
        if not kopf.get(feld):
            raise SystemExit(f"{szenarien.name}: `assistent.{feld}` fehlt im Kopf.")
    profil = {
        "name": kopf["name"],
        "beschreibung": kopf.get("beschreibung") or "",
        "fach": kopf.get("fach", "chemie"),
        "prompt": REPO / kopf["prompt"],
        "min_grade": kopf.get("min_grade"),
        "max_grade": kopf.get("max_grade"),
        "modell": kopf.get("modell", VORGABE_MODELL),
        "ohne": list(kopf.get("ohne", VORGABE_OHNE)),
    }
    # YAML liest `36` als Zahl — Prüfwerte sind immer Text.
    for fall in daten["faelle"]:
        fall["stufenfremd"] = [str(w) for w in fall.get("stufenfremd") or []]
        for zug in fall["zuege"]:
            zug["verboten"] = [str(v) for v in zug.get("verboten") or []]
    return profil, daten["faelle"]


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
        # Stufenvorgriff: ein Wort trifft seine Zusammensetzungen, nicht ein anderes Wort.
        ("Magnesium gibt dabei Elektronen ab.", "Elektron", True),
        ("Das ist eine Elektronenabgabe.", "Elektron", True),
        ("Der elektrische Strom fließt.", "Elektron", False),
        ("Bestimme die Oxidationszahlen.", "Oxidationszahl", True),
        ("Das Oxid entsteht.", "Oxidationszahl", False),
    ]
    for satz, wert, soll in fest:
        ist = bool(vorgriffe(satz, [wert]))
        ok &= ist == soll
        print(f"  {'✓' if ist == soll else '✗'} {'trifft' if soll else 'trifft nicht'}: {wert!r} in {satz!r}")
    print()
    for fall in faelle:
        for w in fall.get("stufenfremd") or []:
            p = bool(vorgriffe(f"Hier geht es um {w}.", [w]))
            ok &= p
            if not p:
                print(f"  ✗ {fall['id']:<40} stufenfremd {w!r} trifft sich selbst nicht")
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


def assistent(conn, profil: dict, prompt_datei: Path | None = None,
              ohne: list[str] | None = None) -> int:
    """Den Assistenten des Profils anlegen oder auf den Stand der Promptdatei bringen.

    Für Experimente: ``prompt_datei`` (eine Variante außerhalb des Repos) und ``ohne``
    (abgeschaltete Lernverhalten-Augmentierungen). Ohne beides: die Einrichtung aus dem Kopf der
    Szenariodatei. Der nächste Lauf ohne Optionen stellt sie wieder her."""
    prompt = (prompt_datei or profil["prompt"]).read_text(encoding="utf-8").strip()
    ohne = profil["ohne"] if ohne is None else ohne
    name = profil["name"]
    chemie = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", profil["fach"])
    werte = dict(system_prompt=prompt, subject_id=chemie, audience="student", scope="all_students",
                 status="active", min_grade=profil["min_grade"], max_grade=profil["max_grade"],
                 model=profil["modell"], tool_groups="[]",
                 disabled_augmentations="{" + ",".join(ohne) + "}")
    kennung = _eins(conn, "SELECT id FROM assistants WHERE name = %s", name)
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
                werte | {"name": name, "beschreibung": profil["beschreibung"]},
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


def prompt_stand(prompt: Path, prompt_datei: Path | None = None) -> str:
    """Git-Stand der Promptdatei des Profils (``prompt``); eine Variante wird als solche benannt."""
    prompt_datei = prompt_datei or prompt

    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout.strip()
    if prompt_datei.resolve() != prompt.resolve():
        basis = git("log", "-1", "--format=%h", "--", str(prompt.relative_to(REPO)))
        return f"**Variante** `{prompt_datei.name}` (nicht im Repo; Basis {basis})"
    rel = str(prompt.relative_to(REPO))
    status = git("status", "--porcelain", "--", rel)
    if status.startswith("??"):
        return "unversioniert (noch nicht im Repo)"
    hash_ = git("log", "-1", "--format=%h %cs", "--", rel)
    if not status:
        return hash_
    inhalt = hashlib.sha256(prompt.read_bytes()).hexdigest()[:10]
    return f"{hash_} + uncommittete Änderungen (Inhalt sha256 `{inhalt}`)"


def knoten_der_antwort(conn, konversation: str) -> list[str]:
    """Bausteine der **letzten** Antwort (Vorab und Werkzeug) — `Titel (Herkunft)`."""
    return [f"{t} ({h})" for t, h in _alle(
        conn, "SELECT n.title, m.herkunft FROM message_context_nodes m "
              "JOIN context_nodes n ON n.id = m.node_id WHERE m.message_id = ("
              "SELECT id FROM messages WHERE conversation_id = %s AND role = 'assistant' "
              "ORDER BY created_at DESC LIMIT 1) ORDER BY m.position", konversation)]


def kosten(conn, konversation: str, warten_s: float = 60.0) -> list[dict]:
    """Tokens und Kosten aller Antworten einer Konversation, in Zugreihenfolge.

    Die Kosten trägt das Backend im Hintergrund nach (`cost_status = 'ausstehend'`); deshalb
    wird bis ``warten_s`` gewartet, bis keine Antwort mehr aussteht."""
    import time

    ende = time.monotonic() + warten_s
    while True:
        zeilen = _alle(conn, "SELECT tokens_input, tokens_output, cost_usd, cost_status FROM messages "
                             "WHERE conversation_id = %s AND role = 'assistant' ORDER BY created_at",
                       konversation)
        if not any(z[3] == "ausstehend" for z in zeilen) or time.monotonic() > ende:
            break
        time.sleep(2)
    return [{"ein": z[0], "aus": z[1], "usd": float(z[2]) if z[2] is not None else None, "status": z[3]}
            for z in zeilen]


def prompt_tokens(text: str) -> int | None:
    """Geschätzte Tokenzahl des Assistenten-Prompts (o200k_base, die Kodierung der gpt-oss-/GPT-4o-
    Familie). Eine Schätzung: Das tatsächliche Modell kann anders zerlegen."""
    try:
        import tiktoken
    except ImportError:
        return None
    return len(tiktoken.get_encoding("o200k_base").encode(text))


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
                "stufenvorgriffe": vorgriffe(ergebnis["antwort"], fall.get("stufenfremd")),
                "saetze": saetze_zaehlen(ergebnis["antwort"]),
                **{k: ergebnis[k] for k in ("woerter", "fragezeichen", "ueberschriften", "listenpunkte")},
                "muss": zug.get("muss") or [], "darf_nicht": zug.get("darf_nicht") or [],
            })
            print(f"  {fall['id']} Zug {nr}: {ergebnis['woerter']} Wörter, {ergebnis['fragezeichen']}× ?"
                  f"{'  ⚠️ VORGRIFF ' + ', '.join(t['wert'] for t in zuege[-1]['vorgriffe']) if zuege[-1]['vorgriffe'] else ''}"
                  f"{'  ⚠️ STUFE ' + ', '.join(t['wert'] for t in zuege[-1]['stufenvorgriffe']) if zuege[-1]['stufenvorgriffe'] else ''}",
                  flush=True)
    return {"id": fall["id"], "titel": fall["titel"], "stufe": fall["stufe"], "referenz": fall.get("referenz"),
            "konversation": konversation, "zuege": zuege}


# ── Protokoll ────────────────────────────────────────────────────────────────


def _zitat(text: str) -> str:
    return "\n".join(f"> {z}" if z else ">" for z in (text or "*(leer)*").splitlines())


def protokoll(kopf: dict, faelle: list[dict]) -> str:
    name = kopf["name"]
    stufen = f"Kl. {kopf['min_grade'] or '?'}–{kopf['max_grade'] or '?'}"
    t = [f"# {name} — Lauf {kopf['lauf']}", "",
         f"- **Datum:** {kopf['datum']}", f"- **Modell:** {kopf['modell']}",
         f"- **Assistent:** „{name}“, ID {kopf['assistent']} ({kopf.get('fach', 'chemie')}, Schüler:innen, {stufen}, ohne Wissensbereich, "
         "ohne Fähigkeiten, " + (f"**Augmentierungen aus: {', '.join(kopf['ohne'])}**)" if kopf.get("ohne")
                                  else "alle Lernverhalten-Augmentierungen an)"),
         f"- **Prompt-Stand:** `{kopf['prompt_datei']}` {kopf['prompt']}"
         + (f" · etwa {kopf['prompt_tokens']} Tokens (o200k_base)" if kopf.get("prompt_tokens") else ""),
         f"- **Importstand:** {kopf['import']}",
         "- **Schüler:innen-Konto:** Dev-Konto ohne Unterrichtsgruppe, Stufe je Fall im Token; Chat über den "
         "Assistenten (Fach Chemie aus dem Assistenten)",
         "", "Automatisch: **Vorgriff** (verbotene Werte, normalisiert; Treffer mit Satz), **Stufenvorgriff** "
         "(Begriffe, die in der Stufe des Falls noch nicht dran sind), **Kosten**, Fragezeichen (Soll ≤ 1), "
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
            for v in z.get("stufenvorgriffe") or []:
                t.append(f"- ⚠️ **Stufenvorgriff „{v['wert']}“:** " + " · ".join(f"„{s}“" for s in v["saetze"]))
            if z.get("kosten"):
                k = z["kosten"]
                t.append(f"- **Kosten:** {k['ein'] or '?'} Tokens ein, {k['aus'] or '?'} aus, "
                         + (f"{k['usd']:.4f} USD" if k["usd"] is not None else "Kosten unbekannt")
                         + (f" ({k['status']})" if k.get("status") not in (None, "vollstaendig") else ""))
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
    stufe = [(i, z) for i, z in zuege if z.get("stufenvorgriffe")]
    t.append(f"- **Stufenvorgriffe:** {len(stufe)} Züge"
             + ("" if not stufe else " — " + "; ".join(
                 f"{i} Zug {z['nr']}: {', '.join(v['wert'] for v in z['stufenvorgriffe'])}" for i, z in stufe)))
    t += kosten_zusammenfassung(kopf, zuege)
    return "\n".join(t) + "\n"


def kosten_zusammenfassung(kopf: dict, zuege: list[tuple[str, dict]]) -> list[str]:
    """Summe, Mittel und der Anteil des Prompts an den Eingabetokens."""
    k = [z["kosten"] for _, z in zuege if z.get("kosten")]
    ein = [x["ein"] for x in k if x.get("ein")]
    usd = [x["usd"] for x in k if x.get("usd") is not None]
    if not ein:
        return ["- **Kosten:** keine Angaben in `messages`"]
    zeilen = [f"- **Kosten:** {sum(usd):.4f} USD für {len(usd)} Züge (Mittel {sum(usd) / len(usd):.4f} USD/Zug)"
              if usd else "- **Kosten:** unbekannt",
              f"- **Eingabetokens je Zug:** Mittel {round(sum(ein) / len(ein))}, kleinster {min(ein)}, "
              f"größter {max(ein)} · Ausgabe Mittel "
              f"{round(sum(x['aus'] for x in k if x.get('aus')) / max(1, sum(1 for x in k if x.get('aus'))))}"]
    if kopf.get("prompt_tokens"):
        anteil = kopf["prompt_tokens"] / (sum(ein) / len(ein))
        zeilen.append(f"- **Anteil des Assistenten-Prompts** an den Eingabetokens: etwa {anteil:.0%} "
                      f"({kopf['prompt_tokens']} von im Mittel {round(sum(ein) / len(ein))}; Schätzung)")
    return zeilen


def main() -> None:
    hauptprogramm()


def hauptprogramm(szenarien: Path | None = None) -> None:
    """Gemeinsamer Einstieg — ``szenarien`` setzt die Vorgabe (Hülle `stoechiometrie_messung.py`)."""
    p = argparse.ArgumentParser(description="Messung eines Schüler-Assistenten mit festen Szenarien")
    p.add_argument("--szenarien", type=Path, default=szenarien, required=szenarien is None,
                   help="Szenariodatei mit Kopf `assistent:` und `faelle:`")
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
    p.add_argument("--prompt", type=Path, default=None, help="Promptvariante statt der im Kopf (Experiment)")
    p.add_argument("--ohne-augmentierung", action="append", default=None, dest="ohne",
                   help="abgeschaltete Lernverhalten-Augmentierungen statt der Einrichtung im Kopf; "
                        "mehrfach möglich, „keine“ = alle an")
    args = p.parse_args()

    profil, faelle = profil_laden(args.szenarien)
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
    kennung = assistent(conn, profil, args.prompt, args.ohne)
    args.ohne = profil["ohne"] if args.ohne is None else args.ohne
    zeile = _alle(conn, "SELECT pseudonym FROM pseudonym_audit WHERE roles::text LIKE '%%student%%' "
                        "AND litellm_key IS NOT NULL AND pseudonym LIKE %s ORDER BY created_at LIMIT 1",
                  (args.konto or "") + "%")
    if not zeile:
        raise SystemExit("Kein Schüler:innen-Konto mit LiteLLM-Schlüssel gefunden.")
    schueler = zeile[0][0]
    jwt = get_jwt_service()
    print(f"\nAssistent {kennung}, Prompt {prompt_stand(profil['prompt'], args.prompt)}, "
          f"ohne {args.ohne or '—'}, {len(faelle)} Fälle\n")

    ergebnisse = []
    try:
        for fall in faelle:
            ergebnisse.append(fall_durchspielen(conn, jwt, schueler, kennung, fall, args.basis, args.modell))
        # Vor dem Löschen: Kosten trägt das Backend im Hintergrund nach.
        for f in ergebnisse:
            if f["konversation"]:
                je_zug = kosten(conn, f["konversation"])
                for z, k in zip([z for z in f["zuege"] if "antwort" in z], je_zug):
                    z["kosten"] = k
    finally:
        if not args.behalten:
            with conn.cursor() as cur:
                for f in ergebnisse:
                    if f["konversation"]:
                        cur.execute("DELETE FROM conversations WHERE id = %s AND pseudonym = %s",
                                    (f["konversation"], schueler))
        conn.close()

    modelle = sorted({z["modell"] for f in ergebnisse for z in f["zuege"] if z.get("modell")})
    prompt_text = (args.prompt or profil["prompt"]).read_text(encoding="utf-8")
    kopf = {"lauf": args.lauf, "datum": datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y, %H:%M"),
            "modell": ", ".join(modelle) or "?", "assistent": kennung, "name": profil["name"], "fach": profil["fach"],
            "min_grade": profil["min_grade"], "max_grade": profil["max_grade"],
            "prompt_datei": str((args.prompt or profil["prompt"]).resolve().relative_to(REPO))
            if (args.prompt or profil["prompt"]).resolve().is_relative_to(REPO) else str(args.prompt),
            "prompt": prompt_stand(profil["prompt"], args.prompt), "prompt_tokens": prompt_tokens(prompt_text),
            "ohne": args.ohne, "import": args.importstand}
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
