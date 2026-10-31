#!/usr/bin/env python3
"""Messung eines Schüler-Assistenten mit festen Szenarien (Muster: Assistent für stöchiometrische Berechnungen).

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

**Planungsdaten je Fall** (Feld `planung`, seit 29.10.2026): Fach, Einheit, vergangene
Stundenthemen (alt → neu) und `klassenarbeit_in_tagen`. Für einen solchen Fall baut das Skript eine
Messgruppe auf (Muster `letzte_stunde_messung.py`: Lehrkraft, die Schüler:in als vorübergehendes
Mitglied, nachbereitete Stunden in der Einheit, ein Prüfungstermin in der Einheit), spielt den Fall
mit Gruppenbezug durch und baut die Gruppe danach wieder ab — samt ihrer Konversation, deshalb
werden die Kosten dieses Falls gleich danach gelesen, und `--behalten` gilt für ihn nicht. Im Chat
steht dann „Klassenarbeit: … — Umfang: <Einheit>" im Block „Aktueller Unterricht".

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
from datetime import date, datetime, timezone
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
        # Päckchen AF: Fächerkreis für den Abschnitt „Operator dieser Aufgabe" (leer = aus).
        "operator_faecher": [str(f) for f in kopf.get("operator_faecher") or []],
        # 0.26: Bausteine hinter dem Prompt (`app/assistants/bausteine/`).
        "bausteine": [str(b) for b in kopf.get("bausteine") or []],
    }
    # YAML liest `36` als Zahl — Prüfwerte sind immer Text.
    for fall in daten["faelle"]:
        fall["stufenfremd"] = [str(w) for w in fall.get("stufenfremd") or []]
        for zug in fall["zuege"]:
            if zug.get("operator") is not None:
                zug["operator"] = [str(o) for o in zug["operator"]]
        if fall.get("planung"):
            fall["planung"]["themen"] = [str(t) for t in fall["planung"].get("themen") or []]
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
letzte = _lade("letzte_stunde_messung")
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
              ohne: list[str] | None = None, operator_faecher: list[str] | None = None) -> int:
    """Den Assistenten des Profils anlegen oder auf den Stand der Promptdatei bringen.

    Für Experimente: ``prompt_datei`` (eine Variante außerhalb des Repos) und ``ohne``
    (abgeschaltete Lernverhalten-Augmentierungen). Ohne beides: die Einrichtung aus dem Kopf der
    Szenariodatei. Der nächste Lauf ohne Optionen stellt sie wieder her."""
    prompt = (prompt_datei or profil["prompt"]).read_text(encoding="utf-8").strip()
    ohne = profil["ohne"] if ohne is None else ohne
    name = profil["name"]
    # `fach: null` im Kopf = fachübergreifend (Rückfall-Assistenten).
    chemie = (_eins(conn, "SELECT id FROM subjects WHERE slug = %s", profil["fach"])
              if profil["fach"] else None)
    werte = dict(system_prompt=prompt, subject_id=chemie, audience="student", scope="all_students",
                 status="active", min_grade=profil["min_grade"], max_grade=profil["max_grade"],
                 model=profil["modell"], tool_groups="[]",
                 disabled_augmentations="{" + ",".join(ohne) + "}",
                 # Nur Fächer, die es hier gibt — wie der Seed (`nit` kommt erst 2027/28).
                 operator_faecher=json.dumps([
                     f for f in (profil["operator_faecher"] if operator_faecher is None else operator_faecher)
                     if _eins(conn, "SELECT 1 FROM subjects WHERE slug = %s", f)]),
                 bausteine=json.dumps(profil.get("bausteine") or []))
    kennung = _eins(conn, "SELECT id FROM assistants WHERE name = %s", name)
    with conn.cursor() as cur:
        if kennung is None:
            cur.execute(
                "INSERT INTO assistants (name, description, system_prompt, subject_id, audience, scope, status, "
                "min_grade, max_grade, model, tool_groups, disabled_augmentations, operator_faecher, bausteine, visibility, "
                "tags, created_by, creator_role, created_at, updated_at) VALUES "
                "(%(name)s, %(beschreibung)s, %(system_prompt)s, %(subject_id)s, %(audience)s, %(scope)s, "
                "%(status)s, %(min_grade)s, %(max_grade)s, %(model)s, %(tool_groups)s::jsonb, "
                "%(disabled_augmentations)s::text[], %(operator_faecher)s::jsonb, %(bausteine)s::jsonb, 'public', '{}'::text[], "
                "'__messung__', 'admin', now(), now()) "
                "RETURNING id",
                werte | {"name": name, "beschreibung": profil["beschreibung"]},
            )
            kennung = cur.fetchone()[0]
        else:
            cur.execute(
                "UPDATE assistants SET system_prompt = %(system_prompt)s, subject_id = %(subject_id)s, "
                "audience = %(audience)s, scope = %(scope)s, status = %(status)s, min_grade = %(min_grade)s, "
                "max_grade = %(max_grade)s, model = %(model)s, tool_groups = %(tool_groups)s::jsonb, "
                "disabled_augmentations = %(disabled_augmentations)s::text[], "
                "operator_faecher = %(operator_faecher)s::jsonb, bausteine = %(bausteine)s::jsonb, "
                "updated_at = now() WHERE id = %(id)s",
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


# ── Messgruppe für Fälle mit Planung ─────────────────────────────────────────

#: Die Messgruppe der Fälle mit `planung` — eine feste Kennung neben denen der anderen
#: Messungen (98015–98017); `entfall.abbauen` prüft den Namen, bevor es löscht.
MESSGRUPPE = {"id": 98018, "name": "Messung Assistent mit Planung"}


def planung_text(planung: dict) -> str:
    """Die Planungsdaten eines Falls in einer Zeile — für Protokollkopf und Konsole."""
    return (f"Fach {planung['fach']}, Einheit „{planung['einheit']}“, Stunden: "
            f"{' · '.join(planung['themen']) or '—'}, Klassenarbeit in {planung['klassenarbeit_in_tagen']} Tagen")


def planung_aufbauen(conn, jwt, planung: dict, schueler: str, basis: str, heute):
    """Messgruppe mit nachbereiteten Stunden der Einheit und einer Klassenarbeit darin.

    Die Klassenarbeit trägt die Einheit selbst (`ue_node_id`) — so ist ihr Umfang die Einheit
    (`student_context.get_exam_scope`), unabhängig von anderen Terminen. Liefert die Gruppe und
    den Block „Aktueller Unterricht", wie ihn der Chat sieht."""
    from datetime import timedelta

    from app.planning.calendar import load_school_year

    entfall.abbauen(conn, MESSGRUPPE)
    gid = MESSGRUPPE["id"]
    lehrer = _alle(conn, "SELECT pseudonym FROM pseudonym_audit WHERE roles::text LIKE '%%teacher%%' "
                         "ORDER BY created_at LIMIT 1")
    if not lehrer:
        raise SystemExit("Kein Lehrkraft-Konto für die Messgruppe gefunden.")
    lehrer = lehrer[0][0]
    fach_id = _eins(conn, "SELECT id FROM subjects WHERE slug = %s", planung["fach"])
    if fach_id is None:
        raise SystemExit(f"Fach {planung['fach']} fehlt — falsche Instanz?")
    wechsel = load_school_year().halbjahreswechsel
    # Werktage vor heute, je Thema einer — die Wochentage sind hier gleichgültig.
    vergangen, _ = letzte.termine([0, 1, 2, 3, 4], heute, len(planung["themen"]), 0)
    arbeit = heute + timedelta(days=int(planung["klassenarbeit_in_tagen"]))
    with conn.cursor() as cur:
        cur.execute("INSERT INTO groups (id, name, slug, type, subject_id) VALUES (%s, %s, %s, 'teaching_group', %s)",
                    (gid, MESSGRUPPE["name"], f"messung-planung-{gid}", fach_id))
        cur.execute("INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft) VALUES "
                    "(%s, %s, 'teacher', 'eigen'), (%s, %s, 'student', 'manuell')", (gid, lehrer, gid, schueler))
        for tag in vergangen:
            cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr) "
                        "VALUES (%s, %s, 3, 1, %s)", (gid, tag, 1 if tag < wechsel else 2))
    slots = {d: s for s, d in _alle(conn, "SELECT id::text, date FROM lesson_slots WHERE group_id = %s", gid)}
    token = jwt.issue(pseudonym=lehrer, roles=["teacher"], grade=None)[0]

    def ok(resp):
        if resp.status_code >= 300:
            raise SystemExit(f"Aufbau Planung: {resp.request.method} {resp.request.url.path} → "
                             f"{resp.status_code} {resp.text[:300]}")
        return resp.json()

    with httpx.Client(base_url=basis, timeout=60.0, headers={"Cookie": f"session={token}"}) as lehrkraft:
        ue = ok(lehrkraft.post(f"/planning/groups/{gid}/units", json={"titel": planung["einheit"], "farbe": 0}))["id"]
        for tag, thema in zip(vergangen, planung["themen"]):
            ok(lehrkraft.patch(f"/planning/slots/{slots[tag]}", json={"ue_node_id": ue, "thema": thema}))
            ok(lehrkraft.post(f"/planning/slots/{slots[tag]}/lesson"))
            letzte.nachbereiten(lehrkraft, slots[tag])
    with conn.cursor() as cur:
        cur.execute("INSERT INTO lesson_slots (group_id, date, start_period, periods, halbjahr, kategorie, ue_node_id) "
                    "VALUES (%s, %s, 3, 1, %s, 'pruefung', %s)", (gid, arbeit, 1 if arbeit < wechsel else 2, ue))
    return gid, letzte.block(gid)


def planung_abbauen(conn) -> None:
    entfall.abbauen(conn, MESSGRUPPE)


#: Ton (Arbeitsanweisung Lauf 2, E1/E4): gezählt wie die Fragezeichen.
#: Lauf 3, A2: „du … musst“ im selben Satz zählt mit; „Möchtest/Willst du“ nur im letzten Satz.
_MUSST = re.compile(r"\b(?:musst du|du\b[^.!?\n]*?\bmusst)\b", re.I)
_ANHAENGSEL = re.compile(r"\b(?:möchtest du|willst du)\b[^.!?]*\?\s*$", re.I)
_FETT = re.compile(r"\*\*[^*\n]+\*\*|__[^_\n]+__")


def ton_zaehlen(antwort: str) -> dict:
    """„musst du“, „Möchtest du / Willst du“ und Fettungen in einer Antwort."""
    return {"musst": len(_MUSST.findall(antwort or "")), "anhaengsel": len(_ANHAENGSEL.findall((antwort or "").strip())),
            "fett": len(_FETT.findall(antwort or ""))}


def litellm_ausgaben(pseudonym: str) -> float | None:
    """Bisherige Ausgaben des Kontos laut LiteLLM (Master-Key) — vor und nach dem Lauf gelesen.

    Lauf 3, A3: Die Kosten je Zug aus `messages` sind oft unvollständig (der erste Zug eines
    Falls stand mit 0,0001 USD — vermutlich nur die Titelerzeugung, weil die SpendLogs der
    eigentlichen Antwort beim Nachtragen noch fehlten). Der Kontostand ist die verlässliche Summe."""
    try:
        with httpx.Client(base_url=settings.litellm_proxy_url, timeout=20.0,
                          headers={"Authorization": f"Bearer {settings.litellm_master_key}"}) as litellm:
            antwort = litellm.get("/user/info", params={"user_id": pseudonym})
        info = (antwort.json().get("user_info") or {}) if antwort.status_code == 200 else {}
        return float(info["spend"]) if info.get("spend") is not None else None
    except (httpx.HTTPError, ValueError):
        return None


def kosten_eintragen(conn, ergebnis: dict) -> None:
    """Kosten je Zug aus `messages` an die beantworteten Züge eines Falls hängen."""
    if ergebnis["konversation"]:
        je_zug = kosten(conn, ergebnis["konversation"])
        for z, k in zip([z for z in ergebnis["zuege"] if "antwort" in z], je_zug):
            z["kosten"] = k


# ── Lauf ─────────────────────────────────────────────────────────────────────


def fall_durchspielen(conn, jwt, schueler: str, kennung: int, fall: dict, basis: str,
                      modell: str | None = None, vorlauf: list[str] | None = None,
                      gruppe: int | None = None) -> dict:
    """``vorlauf``: Schülernachrichten, die **im Standard-Chat** (ohne Assistent) vorausgehen; ab dem
    ersten Zug des Falls übernimmt der Assistent dieselbe Konversation (Wechsel nach ADR-005 — der
    Versuch zu C1 Schritt 6). Vorlauf-Züge stehen im Protokoll, zählen aber nicht mit.
    ``gruppe``: Gruppenbezug der neuen Konversation (Fälle mit `planung`)."""
    token = jwt.issue(pseudonym=schueler, roles=["student"], grade=str(fall["stufe"]))[0]
    zuege, verlauf, konversation = [], [], None
    with httpx.Client(base_url=basis, timeout=300.0, headers={"Cookie": f"session={token}"}) as client:
        for nr, text in enumerate(vorlauf or [], start=1):
            try:
                ergebnis = chat_probe.frage_stellen(client, text, assistent=None, gruppe=gruppe,
                                                    verlauf=verlauf, konversation=konversation)
            except (httpx.HTTPError, SystemExit) as fehler:
                zuege.append({"nr": f"V{nr}", "vorlauf": True, "schueler": text,
                              "abbruch": f"{type(fehler).__name__}: {fehler}"})
                return {"id": fall["id"], "titel": fall["titel"], "stufe": fall["stufe"],
                        "referenz": fall.get("referenz"), "konversation": konversation, "zuege": zuege,
                        "planung": fall.get("planung")}
            konversation = ergebnis["konversation"]
            verlauf += [{"role": "user", "content": text}, {"role": "assistant", "content": ergebnis["antwort"]}]
            zuege.append({"nr": f"V{nr}", "vorlauf": True, "schueler": text, "antwort": ergebnis["antwort"],
                          "modell": ergebnis["modell"], "fehler": ergebnis["fehler"], "werkzeuge": [],
                          "angebot": [], "suchanfragen": [], "aufzaehlungen": [], "knoten": [],
                          "vorgriffe": [], "stufenvorgriffe": [], "saetze": 0, "muss": [], "darf_nicht": [],
                          **{k: ergebnis[k] for k in ("woerter", "fragezeichen", "ueberschriften", "listenpunkte")}})
            print(f"  {fall['id']} Vorlauf {nr}: {ergebnis['woerter']} Wörter ({ergebnis['modell']})", flush=True)
        for nr, zug in enumerate(fall["zuege"], start=1):
            try:
                ergebnis = chat_probe.frage_stellen(client, zug["schueler"], assistent=kennung, gruppe=gruppe,
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
                "aufzaehlungen": (ergebnis.get("vorab_debug") or {}).get("aufzaehlungen", []),
                "operator": (ergebnis.get("vorab_debug") or {}).get("operator"),
                "systemtext": (ergebnis.get("vorab_debug") or {}).get("systemtext"),
                "druck": (ergebnis.get("vorab_debug") or {}).get("druck"),
                "lehrkraft": (ergebnis.get("vorab_debug") or {}).get("lehrkraft"),
                "operator_soll": zug.get("operator"),
                "werkzeug_soll": zug.get("werkzeug"),
                "knoten": knoten_der_antwort(conn, konversation),
                "vorgriffe": vorgriffe(ergebnis["antwort"], zug.get("verboten")),
                "stufenvorgriffe": vorgriffe(ergebnis["antwort"], fall.get("stufenfremd")),
                "saetze": saetze_zaehlen(ergebnis["antwort"]),
                **ton_zaehlen(ergebnis["antwort"]),
                **{k: ergebnis[k] for k in ("woerter", "fragezeichen", "ueberschriften", "listenpunkte")},
                "muss": zug.get("muss") or [], "darf_nicht": zug.get("darf_nicht") or [],
            })
            print(f"  {fall['id']} Zug {nr}: {ergebnis['woerter']} Wörter, {ergebnis['fragezeichen']}× ?"
                  f"{'  ⚠️ VORGRIFF ' + ', '.join(t['wert'] for t in zuege[-1]['vorgriffe']) if zuege[-1]['vorgriffe'] else ''}"
                  f"{'  ⚠️ STUFE ' + ', '.join(t['wert'] for t in zuege[-1]['stufenvorgriffe']) if zuege[-1]['stufenvorgriffe'] else ''}",
                  flush=True)
    return {"id": fall["id"], "titel": fall["titel"], "stufe": fall["stufe"], "referenz": fall.get("referenz"),
            "konversation": konversation, "zuege": zuege, "planung": fall.get("planung")}


# ── Protokoll ────────────────────────────────────────────────────────────────


def _zitat(text: str) -> str:
    return "\n".join(f"> {z}" if z else ">" for z in (text or "*(leer)*").splitlines())


def protokoll(kopf: dict, faelle: list[dict]) -> str:
    name = kopf["name"]
    stufen = f"Kl. {kopf['min_grade'] or '?'}–{kopf['max_grade'] or '?'}"
    t = [f"# {name} — Lauf {kopf['lauf']}", "",
         f"- **Datum:** {kopf['datum']}", f"- **Modell:** {kopf['modell']}",
         f"- **Assistent:** „{name}“, ID {kopf['assistent']} ({kopf.get('fach') or 'fachübergreifend'}, Schüler:innen, {stufen}, ohne Wissensbereich, "
         "ohne zuschaltbare Fähigkeiten (die Kontextsuche ist immer an), " + (f"**Augmentierungen aus: {', '.join(kopf['ohne'])}**)" if kopf.get("ohne")
                                  else "alle Lernverhalten-Augmentierungen an)"),
         f"- **Prompt-Stand:** `{kopf['prompt_datei']}` {kopf['prompt']}"
         + (f" · etwa {kopf['prompt_tokens']} Tokens (o200k_base)" if kopf.get("prompt_tokens") else ""),
         f"- **Importstand:** {kopf['import']}",
         *(["- **Systemtext-Zusatz je Fall** (Feld `systemtext_zusatz`, an den Prompt des Assistenten gehängt)"]
           if kopf.get("systemtext_zusatz") else []),
         *(["- **Vorlauf im Standard-Chat** (danach Wechsel zum Assistenten in derselben Konversation): "
            + " · ".join(f"„{v}“" for v in kopf["vorlauf"])] if kopf.get("vorlauf") else []),
         "- **Schüler:innen-Konto:** Dev-Konto ohne Unterrichtsgruppe, Stufe je Fall im Token; Chat über den "
         + (f"Assistenten (Fach {kopf['fach']} aus dem Assistenten)" if kopf.get("fach")
            else "Assistenten (fachübergreifend, Konversation ohne Fach)"),
         "", "Automatisch: **Vorgriff** (verbotene Werte, normalisiert; Treffer mit Satz), **Stufenvorgriff** "
         "(Begriffe, die in der Stufe des Falls noch nicht dran sind), **Kosten**, Fragezeichen (Soll ≤ 1), "
         "Sätze, Wörter, Listenpunkte, Überschriften. Die Kriterien darunter prüft Jan.", ""]
    for f in faelle:
        t += ["---", "", f"## {f['id']} — {f['titel']} (Kl. {f['stufe']})", "",
              f"*Referenz:* {f['referenz'] or '—'}", ""]
        if f.get("planung"):
            t += [f"*Planung (Messgruppe mit Gruppenbezug):* {planung_text(f['planung'])}", ""]
            if f.get("planung_block"):
                t += ["```", f["planung_block"], "```", ""]
        for z in f["zuege"]:
            t += [f"### {'Vorlauf (Standard-Chat) ' if z.get('vorlauf') else 'Zug '}{z['nr']}", "",
                  f"**Schüler:in:** {z['schueler']}", ""]
            if "abbruch" in z:
                t += [f"⚠️ abgebrochen — {z['abbruch']}", ""]
                continue
            t += [_zitat(z["antwort"]), ""]
            befund = [f"{z['fragezeichen']}× ?{' ⚠️' if z['fragezeichen'] > 1 else ''}", f"{z['saetze']} Sätze",
                      f"{z['woerter']} Wörter", f"{z['listenpunkte']} Listenpunkte", f"{z['ueberschriften']} Überschriften"]
            befund += [f"⚠️ {z[k]}× {etikett}" for k, etikett in
                       (("musst", "„musst du“"), ("anhaengsel", "„Möchtest/Willst du“"), ("fett", "Fettdruck"))
                       if z.get(k)]
            t.append("- **Befund:** " + " · ".join(befund))
            for feld, name in (("lehrkraft", "Lehrkraft-Auslöser"), ("druck", "Nachsetz-Auslöser")):
                b = z.get(feld) or {}
                if b.get("treffer") or b.get("anweisung"):
                    t.append(f"- **{name}:** {'Anweisung gesetzt' if b.get('anweisung') else 'Treffer ohne Anweisung'}"
                             f" (Quelle {b.get('quelle') or '—'}, Abstand {b.get('abstand')}, Gegen {b.get('gegen')},"
                             f" Treffer in {b.get('zaehler')} der letzten drei)")
            if z.get("systemtext") is not None:
                st = z["systemtext"]
                t.append(f"- **Systemtext:** Bausteine {', '.join(st.get('bausteine') or []) or '—'} · "
                         f"Andere allgemeine Assistenten: {len(st.get('andere_assistenten') or [])}"
                         + (f" ({', '.join(st['andere_assistenten'])})" if st.get("andere_assistenten") else ""))
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
            for a in z.get("aufzaehlungen") or []:
                t.append(f"  - `list_context_nodes`: titel={a.get('titel')!r}, content_type={a.get('content_type')!r}, "
                         f"subject={a.get('subject')!r}, grade={a.get('grade')!r} → gesamt {a.get('gesamt')}, "
                         f"geliefert {a.get('geliefert')}" + (f", Hinweis: {a['hinweis']}" if a.get("hinweis") else ""))
            if z.get("operator") or z.get("operator_soll") is not None:
                op = z.get("operator") or {}
                erkannt = op.get("operatoren") or []
                zeile = (f"**Operator:** {', '.join(erkannt) or '—'}"
                         + (f" ({', '.join(op.get('faecher') or [])}; {', '.join(op.get('fassungen') or [])})"
                            if erkannt else ""))
                if z.get("operator_soll") is not None:
                    ok = erkannt == z["operator_soll"]
                    zeile = (f"{'✓' if ok else '⚠️'} {zeile}"
                             + ("" if ok else f" — Soll: {', '.join(z['operator_soll']) or 'keiner'}"))
                t.append(f"- {zeile}")
            if z.get("werkzeug_soll"):
                ok = z["werkzeug_soll"] in z["werkzeuge"]
                t.append(f"- {'✓' if ok else '⚠️'} **Soll-Werkzeug `{z['werkzeug_soll']}`:** "
                         f"{'aufgerufen' if ok else 'NICHT aufgerufen'}")
            t.append(f"- **Angeboten:** {', '.join(z['angebot']) or '—'} · **Eingesetzt:** {', '.join(z['knoten']) or '—'}")
            if z.get("fehler"):
                t.append(f"- ⚠️ **Fehler im Strom:** {z['fehler']}")
            t.append("")
            if z["muss"] or z["darf_nicht"]:
                t += [f"- [ ] muss: {k}" for k in z["muss"]] + [f"- [ ] darf nicht: {k}" for k in z["darf_nicht"]]
                t.append("- [ ] Zug passt nicht (Assistent hatte etwas anderes gefragt)")
                t.append("")
    t += ["---", "", "## Zusammenfassung (automatisch, ohne Bewertung der Kriterien)", ""]
    zuege = [(f["id"], z) for f in faelle for z in f["zuege"] if "antwort" in z and not z.get("vorlauf")]
    mit_vorgriff = [(i, z) for i, z in zuege if z["vorgriffe"]]
    t.append(f"- **Züge:** {len(zuege)} beantwortet, {sum(1 for f in faelle for z in f['zuege'] if 'abbruch' in z)} abgebrochen")
    t.append(f"- **Vorgriffe:** {len(mit_vorgriff)} Züge"
             + ("" if not mit_vorgriff else " — " + "; ".join(
                 f"{i} Zug {z['nr']}: {', '.join(v['wert'] for v in z['vorgriffe'])}" for i, z in mit_vorgriff)))
    mehr = [(i, z) for i, z in zuege if z["fragezeichen"] > 1]
    t.append(f"- **Mehr als ein Fragezeichen:** {len(mehr)} Züge"
             + ("" if not mehr else " — " + "; ".join(f"{i} Zug {z['nr']} ({z['fragezeichen']})" for i, z in mehr)))
    for k, etikett in (("musst", "„musst du“"), ("anhaengsel", "„Möchtest/Willst du“"), ("fett", "Fettdruck")):
        mit = [(i, z) for i, z in zuege if z.get(k)]
        t.append(f"- **{etikett}:** {len(mit)} Züge"
                 + ("" if not mit else " — " + "; ".join(f"{i} Zug {z['nr']}" for i, z in mit)))
    st = [z["systemtext"] for _, z in zuege if z.get("systemtext") is not None]
    if st:
        ohne = sum(1 for x in st if not x.get("andere_assistenten"))
        t.append(f"- **Abschnitt „Andere allgemeine Assistenten“:** in {len(st) - ohne} von {len(st)} Zügen")
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
    t += werkzeug_zusammenfassung(zuege)
    t += operator_zusammenfassung(zuege)
    t += kosten_zusammenfassung(kopf, zuege)
    return "\n".join(t) + "\n"


def operator_zusammenfassung(zuege: list[tuple[str, dict]]) -> list[str]:
    """Erkennung gegen das Soll (Feld `operator` je Zug, Päckchen AF) und wie oft ein Abschnitt kam."""
    soll = [(i, z) for i, z in zuege if z.get("operator_soll") is not None]
    mit = [z for _, z in zuege if (z.get("operator") or {}).get("operatoren")]
    if not soll and not mit:
        return []
    falsch = [f"{i} Zug {z['nr']}" for i, z in soll
              if ((z.get("operator") or {}).get("operatoren") or []) != z["operator_soll"]]
    zeilen = [f"- **Operator-Abschnitt:** in {len(mit)} Zügen"]
    if soll:
        zeilen.append(f"- **Operator erkannt wie Soll:** {len(soll) - len(falsch)} von {len(soll)}"
                      + (f" — abweichend: {'; '.join(falsch)}" if falsch else ""))
    return zeilen


def werkzeug_zusammenfassung(zuege: list[tuple[str, dict]]) -> list[str]:
    """Soll-Werkzeuge (Feld `werkzeug` je Zug) — „Operator nachgeschlagen: n von m“."""
    soll = [(i, z) for i, z in zuege if z.get("werkzeug_soll")]
    if not soll:
        return []
    zeilen = []
    for name in sorted({z["werkzeug_soll"] for _, z in soll}):
        mit = [(i, z) for i, z in soll if z["werkzeug_soll"] == name]
        ok = [(i, z) for i, z in mit if name in z["werkzeuge"]]
        fehlt = [f"{i} Zug {z['nr']}" for i, z in mit if name not in z["werkzeuge"]]
        etikett = "Operator nachgeschlagen" if name == "list_context_nodes" else f"`{name}` aufgerufen"
        zeilen.append(f"- **{etikett}:** {len(ok)} von {len(mit)} Soll-Zügen"
                      + (f" — fehlt: {'; '.join(fehlt)}" if fehlt else ""))
    aufrufe = [a for _, z in zuege for a in z.get("aufzaehlungen") or []]
    if aufrufe:
        mit_fach = [a for a in aufrufe if a.get("subject")]
        gesamt = [a["gesamt"] for a in aufrufe if isinstance(a.get("gesamt"), int)]
        zeilen.append(f"- **`list_context_nodes`-Aufrufe:** {len(aufrufe)}, davon mit `subject` {len(mit_fach)}"
                      + (f" ({', '.join(sorted({str(a['subject']) for a in mit_fach}))})" if mit_fach else "")
                      + (f"; Treffer je Aufruf Mittel {round(sum(gesamt) / len(gesamt))}, größter {max(gesamt)}"
                         if gesamt else ""))
    return zeilen


def kosten_zusammenfassung(kopf: dict, zuege: list[tuple[str, dict]]) -> list[str]:
    """Summe, Mittel und der Anteil des Prompts an den Eingabetokens."""
    k = [z["kosten"] for _, z in zuege if z.get("kosten")]
    ein = [x["ein"] for x in k if x.get("ein")]
    # Lauf 2, E1: Nur vollständige Kosten zählen ins Mittel; Teilwerte gelten als unvollständig.
    voll = [x["usd"] for x in k if x.get("usd") is not None and x.get("status") in (None, "vollstaendig")]
    if not ein:
        return ["- **Kosten:** keine Angaben in `messages`"]
    rest = len(zuege) - len(voll)
    zeilen = [f"- **Kosten:** Mittel {sum(voll) / len(voll):.4f} USD/Zug aus {len(voll)} vollständigen Zügen"
              + (f"; {rest} unvollständig — hochgerechnet {sum(voll) / len(voll) * len(zuege):.4f} USD "
                 f"für {len(zuege)} Züge" if rest else f", zusammen {sum(voll):.4f} USD")
              if voll else "- **Kosten:** unbekannt",
              f"- **Eingabetokens je Zug:** Mittel {round(sum(ein) / len(ein))}, kleinster {min(ein)}, "
              f"größter {max(ein)} · Ausgabe Mittel "
              f"{round(sum(x['aus'] for x in k if x.get('aus')) / max(1, sum(1 for x in k if x.get('aus'))))}"]
    if kopf.get("kosten_litellm") is not None and zuege:
        zeilen.insert(0, f"- **Kosten laut LiteLLM** (Konto vor und nach dem Lauf): {kopf['kosten_litellm']:.4f} USD "
                         f"für {len(zuege)} Züge ({kopf['kosten_litellm'] / len(zuege):.4f} USD/Zug)")
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
    p.add_argument("--systemtext-zusatz", action="store_true", dest="systemtext_zusatz",
                   help="Feld `systemtext_zusatz` eines Falls an den Prompt des Assistenten hängen (nur für "
                        "diesen Fall) — Versuch Prüfregel Arm B: Operator-Definition im Systemtext")
    p.add_argument("--vorlauf", type=Path, default=None,
                   help="YAML-Liste von Schülernachrichten, die im Standard-Chat vorausgehen; danach Wechsel "
                        "zum Assistenten in derselben Konversation (C1 Schritt 6)")
    p.add_argument("--ohne-augmentierung", action="append", default=None, dest="ohne",
                   help="abgeschaltete Lernverhalten-Augmentierungen statt der Einrichtung im Kopf; "
                        "mehrfach möglich, „keine“ = alle an")
    args = p.parse_args()

    profil, faelle = profil_laden(args.szenarien)
    vorlauf = ([str(t) for t in yaml.safe_load(args.vorlauf.read_text(encoding="utf-8"))]
               if args.vorlauf else None)
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
    # Mit Handzusatz (Versuch Prüfregel, Arm B) ohne Fächerkreis — sonst stünde die Definition doppelt da.
    kennung = assistent(conn, profil, args.prompt, args.ohne, [] if args.systemtext_zusatz else None)
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
    ausgaben_vorher = litellm_ausgaben(schueler)
    grundprompt = (args.prompt or profil["prompt"]).read_text(encoding="utf-8").strip()
    try:
        for fall in faelle:
            # Arm B des Versuchs Prüfregel: Die Konversation übernimmt den Prompt beim Anlegen
            # (Schnappschuss) — der Zusatz gilt also genau für diesen Fall.
            if args.systemtext_zusatz:
                zusatz = (fall.get("systemtext_zusatz") or "").strip()
                with conn.cursor() as cur:
                    cur.execute("UPDATE assistants SET system_prompt = %s WHERE id = %s",
                                (grundprompt + ("\n\n" + zusatz if zusatz else ""), kennung))
                conn.commit()
            if not fall.get("planung"):
                ergebnisse.append(fall_durchspielen(conn, jwt, schueler, kennung, fall, args.basis, args.modell,
                                                    vorlauf))
                continue
            # Mit Planung: eigene Messgruppe; ihr Abbau löscht die Konversation, die Kosten also vorher.
            try:
                gruppe, block = planung_aufbauen(conn, jwt, fall["planung"], schueler, args.basis, date.today())
                print(f"  {fall['id']} Planung: {planung_text(fall['planung'])}", flush=True)
                ergebnis = fall_durchspielen(conn, jwt, schueler, kennung, fall, args.basis, args.modell,
                                             vorlauf, gruppe=gruppe)
                ergebnis["planung_block"] = block
                kosten_eintragen(conn, ergebnis)
                ergebnisse.append(ergebnis)
            finally:
                planung_abbauen(conn)
        # Vor dem Löschen: Kosten trägt das Backend im Hintergrund nach.
        for f in ergebnisse:
            if not f.get("planung"):
                kosten_eintragen(conn, f)
    finally:
        if args.systemtext_zusatz:
            with conn.cursor() as cur:
                cur.execute("UPDATE assistants SET system_prompt = %s WHERE id = %s", (grundprompt, kennung))
            conn.commit()
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
            "ohne": args.ohne, "import": args.importstand, "vorlauf": vorlauf,
            "systemtext_zusatz": bool(args.systemtext_zusatz)}
    ausgaben_nachher = litellm_ausgaben(schueler)
    if ausgaben_vorher is not None and ausgaben_nachher is not None:
        kopf["kosten_litellm"] = round(ausgaben_nachher - ausgaben_vorher, 6)
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
