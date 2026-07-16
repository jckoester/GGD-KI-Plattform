"""LLM-Struktur-Extraktion aus BP-PDF-Text (KS-Plan C3/C4, Schritt 2).

Ruft den LiteLLM-Proxy (`/chat/completions`) auf und liefert die **neutrale Struktur**
(ohne bp_ids). Die bp_id-/Node-Assemblierung macht `nodes.py` deterministisch (Zweiteilung).
Öffentliche BP-PDFs → datenschutzunkritisch.

Für LFDB (Pilot): 3 Ebenen Baustein → Themenblock → Leitfrage/Kompetenz. pdfminer verwürfelt
die zweispaltige Tabelle; das Modell rekonstruiert die Zuordnung Leitfrage↔Kompetenz↔Impulse.
"""
from __future__ import annotations

import json
import os
import re

import httpx

DEFAULT_MODEL = "claude-opus-4-8"

# Erwartete neutrale Struktur (Dokumentation + Prompt). KEINE bp_ids hier.
_LFDB_SYSTEM = """\
Du extrahierst die Struktur des „Leitfaden Demokratiebildung" (Baden-Württemberg) aus dem
Rohtext einer PDF-Tabelle. Der Text stammt aus zweispaltigen Tabellen und ist dadurch
teils verwürfelt (linke Spalte: Leitfragen + Kompetenzen; rechte Spalte: Impulse & Inhalte).
Rekonstruiere die inhaltliche Zuordnung sorgfältig.

Struktur (drei Ebenen):
- Baustein: Kapitel, überschrieben mit „BAUSTEIN <n> – <TITEL>" (4 Stück).
- Themenblock: benannter Block innerhalb eines Bausteins, mit einer Zeile
  „p Leitperspektive: <Kürzel, Kürzel>" (Kürzel wie BTV, PG, BNE, BO, MB, VB).
- Kompetenz: je eine Leitfrage (Frage) + zugehörige Kompetenz („Die SuS können …") + die
  zugeordneten Impulse/Inhalte (rechte Spalte).

Gib AUSSCHLIESSLICH ein JSON-Objekt in genau dieser Form zurück (keine Erklärungen):
{
  "bausteine": [
    {
      "nummer": 1,
      "titel": "Identität und Pluralismus",
      "themenbloecke": [
        {
          "titel": "Mit Pluralismus umgehen",
          "leitperspektiven": ["BTV", "PG"],
          "kompetenzen": [
            {
              "leitfrage": "Was macht mich aus? Was gehört zu mir?",
              "kompetenz": "Die SuS können Aspekte der eigenen Identität erkennen und benennen.",
              "impulse_inhalte": "Neigungen, Interessen, Vorlieben, ..."
            }
          ]
        }
      ]
    }
  ]
}

Regeln:
- Titel/Texte wörtlich übernehmen, nur offensichtliche Trennfehler (Silbentrennung am
  Zeilenende) glätten.
- `leitperspektiven`: Liste der Kürzel des Themenblocks (leer, wenn keine angegeben).
- Ordne jede Leitfrage/Kompetenz die passenden Impulse/Inhalte zu. Wenn sich mehrere
  Leitfragen einen Impulse-Block teilen, dupliziere den Text sinngemäß je Kompetenz.
- Erfinde nichts; lasse Felder leer, wenn nicht vorhanden.
"""


def _strip_json_fence(content: str) -> str:
    """Entfernt eine Markdown-Codefence (```json … ```), die manche Modelle trotz
    response_format=json_object um die Antwort legen. Ohne Fence unverändert."""
    t = (content or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


def _chat_completion_json(
    text: str,
    *,
    system: str,
    model: str,
    proxy_url: str,
    api_key: str,
    timeout: float = 600.0,
    retries: int = 2,
) -> dict:
    """Ein JSON-Chat-Completion-Aufruf mit Retry. Wiederholt bei
    (a) JSONDecodeError — große Antworten enthalten gelegentlich einen nicht-deterministischen
        JSON-Syntaxfehler (unescaptes Zeichen / fehlendes Komma); ein erneuter Aufruf liefert
        dann gültiges JSON (verifiziert: finish_reason=stop, keine Trunkierung), und
    (b) Timeout/Netzwerkfehler (httpx.TransportError) — große Band-Calls dauern lange, ein
        einzelner Timeout/Verbindungsabriss soll den ganzen Lauf nicht abbrechen.
    HTTP-Statusfehler (z. B. 400 „credit balance too low") propagieren sofort (kein Retry)."""
    if not api_key:
        raise ValueError(
            "LITELLM_MASTER_KEY ist leer/nicht gesetzt — der Authorization-Header wäre "
            "'Bearer ' (ungültig). Umgebung vor dem Aufruf laden, z. B. "
            "`set -a && source .env && set +a`."
        )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    last_exc: Exception | None = None
    for _ in range(retries + 1):
        try:
            resp = httpx.post(
                f"{proxy_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
        except httpx.TransportError as exc:  # Timeout, Verbindungsabriss, DNS etc.
            last_exc = exc
            continue
        content = _strip_json_fence(resp.json()["choices"][0]["message"]["content"])
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            last_exc = exc
    raise ValueError(
        f"Chat-Completion nach {retries + 1} Versuchen fehlgeschlagen: {type(last_exc).__name__}: {last_exc}"
    )


def validate_lfdb_structure(data: dict) -> None:
    """Leichte strukturelle Validierung der neutralen LFDB-Struktur. Wirft ValueError."""
    if not isinstance(data, dict) or not isinstance(data.get("bausteine"), list):
        raise ValueError("Struktur: 'bausteine' (Liste) fehlt")
    if not data["bausteine"]:
        raise ValueError("Struktur: keine Bausteine extrahiert")
    for bi, b in enumerate(data["bausteine"]):
        if not isinstance(b.get("titel"), str) or not b["titel"].strip():
            raise ValueError(f"Baustein {bi}: 'titel' fehlt")
        if not isinstance(b.get("themenbloecke"), list) or not b["themenbloecke"]:
            raise ValueError(f"Baustein {bi} ({b.get('titel')!r}): keine Themenblöcke")
        for ti, t in enumerate(b["themenbloecke"]):
            if not isinstance(t.get("titel"), str) or not t["titel"].strip():
                raise ValueError(f"Baustein {bi}/Themenblock {ti}: 'titel' fehlt")
            if not isinstance(t.get("kompetenzen"), list) or not t["kompetenzen"]:
                raise ValueError(f"Themenblock {t.get('titel')!r}: keine Kompetenzen")
            for ki, k in enumerate(t["kompetenzen"]):
                if not isinstance(k.get("kompetenz"), str) or not k["kompetenz"].strip():
                    raise ValueError(
                        f"Themenblock {t.get('titel')!r}/Kompetenz {ki}: 'kompetenz' fehlt"
                    )


def extract_lfdb_structure(
    text: str,
    *,
    model: str = DEFAULT_MODEL,
    proxy_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Extrahiert die neutrale LFDB-Struktur aus dem PDF-Text via LiteLLM-Proxy."""
    proxy_url = (proxy_url or os.environ.get("LITELLM_PROXY_URL", "http://localhost:4000")).rstrip("/")
    api_key = api_key or os.environ.get("LITELLM_MASTER_KEY", "")
    data = _chat_completion_json(
        text, system=_LFDB_SYSTEM, model=model, proxy_url=proxy_url, api_key=api_key
    )
    validate_lfdb_structure(data)
    return data


# ── Fremdsprachen (C3) ───────────────────────────────────────────────────────
# Die BW-Bildungspläne der modernen Fremdsprachen liegen nur als PDF vor (keine
# HTML-Fassung → der Web-Scraper kann sie nicht ziehen). Ihr Inhaltsmodell ist
# aber identisch zu den HTML-Fächern: Abschnitt 2 = prozessbezogene Kompetenzen,
# Abschnitt 3 = inhaltsbezogene Kompetenzen je Jahrgangsstufe. Der LLM extrahiert
# NUR diese neutrale Struktur (ohne bp_ids); die bp_id-Assemblierung macht
# `fremdsprache.py` deterministisch (Zweiteilung wie beim LFDB).

_FREMDSPRACHE_SYSTEM = """\
Du extrahierst die Kompetenzstruktur eines baden-württembergischen Bildungsplans für eine
moderne Fremdsprache (z. B. Englisch, Französisch) aus dem Rohtext der PDF. Die PDF folgt der
üblichen BW-Gliederung:

- Abschnitt 2 „Prozessbezogene Kompetenzen": nummerierte Kompetenzbereiche (2.1, 2.2, …), je
  mit einer Liste nummerierter Kompetenzen („1. …", „2. …").
- Abschnitt 3 „Inhaltsbezogene Kompetenzen": gegliedert nach Jahrgangsstufen (3.1, 3.2, …),
  jeweils mit einer Überschrift „Klassen 5/6" o. ä. Innerhalb einer Jahrgangsstufe gibt es
  Kompetenzbereiche (3.1.1, 3.1.2, …). Ein Bereich enthält ENTWEDER direkt nummerierte
  Kompetenzen („(1) …", „(2) …") ODER weitere Teilbereiche (3.1.1.1, 3.1.1.2, …), die dann
  die Kompetenzen tragen.

Gib AUSSCHLIESSLICH ein JSON-Objekt in genau dieser Form zurück (keine Erklärungen):
{
  "fach": { "titel": "Englisch als erste Fremdsprache", "leitgedanken": "kurzer Einleitungstext oder \\"\\"" },
  "prozessbezogene_kompetenzbereiche": [
    {
      "nummer": "2.1",
      "titel": "Sprachbewusstheit",
      "kompetenzen": [ { "nummer": 1, "text": "Die Schülerinnen und Schüler können …" } ]
    }
  ],
  "jahrgangsstufen": [
    {
      "nummer": "3.1",
      "titel": "Klassen 5/6",
      "klasse_von": 5,
      "klasse_bis": 6,
      "niveau": null,
      "kompetenzbereiche": [
        {
          "nummer": "3.1.1",
          "titel": "Funktionale kommunikative Kompetenz",
          "beschreibung": "",
          "kompetenzen": [],
          "teilbereiche": [
            {
              "nummer": "3.1.1.1",
              "titel": "Hör-/Hörsehverstehen",
              "beschreibung": "",
              "kompetenzen": [
                { "nummer": 1, "text": "Die SuS können …", "verweise": ["BNE", "MB"] }
              ]
            }
          ]
        }
      ]
    }
  ]
}

Regeln:
- Titel/Kompetenztexte WÖRTLICH übernehmen; nur offensichtliche Silbentrennung am Zeilenende glätten.
- `nummer` der Bereiche/Stufen als String genau wie in der PDF ("2.1", "3.1", "3.1.1", "3.1.1.1").
- `nummer` einer Kompetenz = die Ziffer aus „(1)"/„1." als Ganzzahl (1, 2, 3 …), fortlaufend je Bereich.
- `klasse_von`/`klasse_bis`: Ganzzahlen aus der „Klassen X/Y"-Überschrift (z. B. „Klassen 8/9/10" → 8 und 10).
  Kursstufe: `klasse_von`/`klasse_bis` = 11/12.
- `niveau`: null im Regelfall; für Kursstufen-Abschnitte „Basisfach" → "basis", „Leistungsfach" → "leistung".
- Ein Kompetenzbereich hat ENTWEDER `kompetenzen` (dann `teilbereiche` = []) ODER `teilbereiche`
  (dann seine eigenen `kompetenzen` = []). Nie beides gleichzeitig füllen.
- `verweise`: Liste der Leitperspektiven-Kürzel, die bei einer Kompetenz genannt sind
  (BNE, BTV, PG, BO, MB, VB) — nur das Kürzel (optional mit Aspektnummer wie „BNE 2"), keine Fließtexte.
- Erfinde nichts; lasse `beschreibung`/`leitgedanken` leer, wenn nicht vorhanden.
"""


def validate_fremdsprache_structure(data: dict) -> None:
    """Leichte strukturelle Validierung der neutralen Fremdsprachen-Struktur. Wirft ValueError."""
    if not isinstance(data, dict):
        raise ValueError("Struktur: kein JSON-Objekt")
    fach = data.get("fach")
    if not isinstance(fach, dict) or not str(fach.get("titel", "")).strip():
        raise ValueError("Struktur: 'fach.titel' fehlt")

    pk = data.get("prozessbezogene_kompetenzbereiche")
    if not isinstance(pk, list) or not pk:
        raise ValueError("Struktur: 'prozessbezogene_kompetenzbereiche' (Liste) fehlt/leer")
    for gi, g in enumerate(pk):
        if not str(g.get("nummer", "")).strip() or not str(g.get("titel", "")).strip():
            raise ValueError(f"PK-Bereich {gi}: 'nummer'/'titel' fehlt")
        if not isinstance(g.get("kompetenzen"), list) or not g["kompetenzen"]:
            raise ValueError(f"PK-Bereich {g.get('nummer')!r}: keine Kompetenzen")

    js = data.get("jahrgangsstufen")
    if not isinstance(js, list) or not js:
        raise ValueError("Struktur: 'jahrgangsstufen' (Liste) fehlt/leer")
    for si, s in enumerate(js):
        if not str(s.get("nummer", "")).strip():
            raise ValueError(f"Jahrgangsstufe {si}: 'nummer' fehlt")
        if not isinstance(s.get("klasse_von"), int) or not isinstance(s.get("klasse_bis"), int):
            raise ValueError(f"Jahrgangsstufe {s.get('nummer')!r}: 'klasse_von'/'klasse_bis' keine Ganzzahl")
        bereiche = s.get("kompetenzbereiche")
        if not isinstance(bereiche, list) or not bereiche:
            raise ValueError(f"Jahrgangsstufe {s.get('nummer')!r}: keine Kompetenzbereiche")
        for b in bereiche:
            if not str(b.get("nummer", "")).strip() or not str(b.get("titel", "")).strip():
                raise ValueError(f"Kompetenzbereich in {s.get('nummer')!r}: 'nummer'/'titel' fehlt")
            komp = b.get("kompetenzen") or []
            teil = b.get("teilbereiche") or []
            if not komp and not teil:
                raise ValueError(
                    f"Kompetenzbereich {b.get('nummer')!r}: weder Kompetenzen noch Teilbereiche"
                )
            for t in teil:
                if not str(t.get("nummer", "")).strip() or not (t.get("kompetenzen") or []):
                    raise ValueError(
                        f"Teilbereich {t.get('nummer')!r} in {b.get('nummer')!r}: 'nummer' oder Kompetenzen fehlen"
                    )


def extract_fremdsprache_structure(
    text: str,
    *,
    model: str = DEFAULT_MODEL,
    proxy_url: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Extrahiert die neutrale Fremdsprachen-Struktur aus dem PDF-Text via LiteLLM-Proxy.

    Einzel-Call — geeignet für kleine PDFs/Tests. Große Fächer (mehrere Jahrgangsbänder)
    laufen über `extract_fremdsprache_chunked` (band-weise, robuster gegen Auslassungen).
    """
    proxy_url = (proxy_url or os.environ.get("LITELLM_PROXY_URL", "http://localhost:4000")).rstrip("/")
    api_key = api_key or os.environ.get("LITELLM_MASTER_KEY", "")
    data = _chat_completion_json(
        text, system=_FREMDSPRACHE_SYSTEM, model=model, proxy_url=proxy_url, api_key=api_key
    )
    validate_fremdsprache_structure(data)
    return data


# ── Band-weises Chunking (große Fremdsprachen-PDFs) ──────────────────────────
# Der ganze BP (Abschnitt 2 + alle Jahrgangsbänder) ist für einen einzigen LLM-Call zu
# groß und provoziert Auslassungen. Daher: Abschnitt 2 und jedes Band 3.x werden anhand
# ihrer Überschriften deterministisch abgegrenzt und EINZELN extrahiert; Klassen/Niveau
# je Band setze ich aus der Überschrift (nicht das LLM), das LLM liefert nur den
# Kompetenzbaum. Die Teil-Ergebnisse werden zur vollständigen Struktur gemergt.

_FS_PK_SYSTEM = """\
Du extrahierst Abschnitt 2 „Prozessbezogene Kompetenzen" eines baden-württembergischen
Fremdsprachen-Bildungsplans aus dem PDF-Rohtext. Der Abschnitt hat nummerierte
Kompetenzbereiche (2.1, 2.2, …), jeder mit einer Liste von Einzelkompetenzen
(„Die Schülerinnen und Schüler …").

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück (keine Erklärungen):
{
  "prozessbezogene_kompetenzbereiche": [
    { "nummer": "2.1", "titel": "Sprachbewusstheit",
      "kompetenzen": [ { "nummer": 1, "text": "Die Schülerinnen und Schüler …" } ] }
  ]
}

Regeln:
- Titel/Texte WÖRTLICH übernehmen; nur Silbentrennung am Zeilenende glätten.
- `nummer` der Bereiche als String genau wie in der PDF ("2.1", "2.2", …).
- `nummer` der Kompetenzen: fortlaufende Ganzzahl je Bereich, beginnend bei 1
  (auch wenn die PDF sie nicht nummeriert — je eigenständige Kompetenz eine Ziffer).
- Erfinde nichts.
"""

_FS_BAND_SYSTEM = """\
Du extrahierst die INHALTSBEZOGENEN Kompetenzen EINER Jahrgangsstufe (Abschnitt 3.x) eines
baden-württembergischen Fremdsprachen-Bildungsplans aus dem PDF-Rohtext. Die Stufe enthält
Kompetenzbereiche (z. B. 3.1.1, 3.1.2, …). Ein Bereich enthält ENTWEDER direkt nummerierte
Kompetenzen („(1) …", „(2) …") ODER weitere Teilbereiche (3.1.3.1, 3.1.3.2, …), die dann
die Kompetenzen tragen.

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück (keine Erklärungen):
{
  "kompetenzbereiche": [
    {
      "nummer": "3.1.1", "titel": "Soziokulturelles Orientierungswissen",
      "beschreibung": "",
      "kompetenzen": [ { "nummer": 1, "text": "Die SuS können …", "verweise": ["BNE", "MB"] } ],
      "teilbereiche": [
        { "nummer": "3.1.3.1", "titel": "Hör-/Hörsehverstehen", "beschreibung": "",
          "kompetenzen": [ { "nummer": 1, "text": "Die SuS können …", "verweise": [] } ] }
      ]
    }
  ]
}

Regeln:
- Titel/Kompetenztexte WÖRTLICH übernehmen; nur Silbentrennung am Zeilenende glätten.
- `nummer` der Bereiche/Teilbereiche als String genau wie in der PDF ("3.1.1", "3.1.3.1").
- `nummer` einer Kompetenz = die Ziffer aus „(1)"/„(2)" als Ganzzahl, fortlaufend je Bereich.
- Ein Bereich hat ENTWEDER `kompetenzen` (dann `teilbereiche` = []) ODER `teilbereiche`
  (dann seine eigenen `kompetenzen` = []). Nie beides.
- `verweise`: NUR Leitperspektiven-Kürzel bei der Kompetenz (BNE, BTV, PG, BO, MB, VB),
  optional mit Aspektnummer („BNE 2"). Verweise auf prozessbezogene Kompetenzen („P 2.1")
  NICHT aufnehmen.
- Die Klassenstufe/Niveau NICHT ausgeben (wird separat gesetzt). Erfinde nichts.
"""

# Überschriften-Erkennung (auf nicht-leeren Zeilen am Seitenanfang).
_PK_HEAD_RE = re.compile(r"^2[.\s]\s*Prozessbezogene\s+Kompetenzen", re.I)
# Band-Überschrift: „Klassen 5/6" oder „Klassen 6/7/8" (Mehrklassen-Band) + optionaler
# Niveau-Zusatz. Gruppe 1 = alle Klassenzahlen (von = erste, bis = letzte).
_BAND_HEAD_RE = re.compile(r"^Klassen\s+(\d+(?:\s*/\s*\d+)+)(.*)$", re.I)
_END_HEAD_RE = re.compile(r"^\d[.\s]\s*Operatoren\b", re.I)
_OP_HEAD_RE = re.compile(r"^(\d)[.\s]\s*Operatoren\b", re.I)
_SECTION_HEAD_RE = re.compile(r"^(\d)[.\s]\s*[A-ZÄÖÜ]")

_OPERATOR_SYSTEM = """\
Du extrahierst die Operatorenliste (Abschnitt „Operatoren") eines baden-württembergischen
Fremdsprachen-Bildungsplans aus dem PDF-Rohtext. Es ist eine zweispaltige Tabelle
Operator | Beschreibung, teils mit einer Spalte Anforderungsbereich (AFB: I, II, III).
pdfminer verwürfelt die Spalten → rekonstruiere die Zuordnung Operator↔Beschreibung↔AFB
sorgfältig.

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück (keine Erklärungen):
{
  "operatoren": [
    { "operator": "(be-)nennen", "beschreibung": "Sachverhalte präzise bezeichnen, aufzählen oder auflisten", "afb": [] },
    { "operator": "begründen", "beschreibung": "Positionen durch Argumente stützen oder widerlegen", "afb": ["II", "III"] }
  ]
}

Regeln:
- `operator`: die Operator-Zelle WÖRTLICH übernehmen (mit Klammern/Kommas/Ergänzungsstrichen,
  z. B. „(be-)nennen", „darstellen, darlegen") — NICHT auftrennen oder normalisieren.
- `beschreibung`: der zugehörige Beschreibungstext, wörtlich; Silbentrennung glätten.
- `afb`: Liste der genannten Anforderungsbereiche (nur „I", „II", „III"); leer [] wenn keiner steht.
- Nur die Operator-Tabelle. Die einleitende AFB-Erläuterung („Anforderungsbereich I umfasst …")
  ist KEIN Operator. Erfinde nichts.
"""


def detect_operator_chunk(pages: list[str]) -> str | None:
    """Grenzt den Operatoren-Abschnitt (z. B. „4. Operatoren") gegen die nächste Top-Level-
    Sektion ab. None, wenn kein Operatoren-Abschnitt existiert."""
    op_start = op_num = None
    for i, page in enumerate(pages):
        for line in _page_top_lines(page):
            if len(line) < 40 and (m := _OP_HEAD_RE.match(line)):
                op_start, op_num = i, int(m.group(1))
                break
        if op_start is not None:
            break
    if op_start is None:
        return None
    op_end = len(pages)
    for i in range(op_start + 1, len(pages)):
        for line in _page_top_lines(pages[i]):
            if len(line) < 40 and (m := _SECTION_HEAD_RE.match(line)) and int(m.group(1)) > op_num:
                op_end = i
                break
        if op_end != len(pages):
            break
    return "\n".join(pages[op_start:op_end])


def _page_top_lines(page: str, n: int = 8) -> list[str]:
    return [ln.strip() for ln in page.splitlines() if ln.strip()][:n]


def detect_fremdsprache_chunks(pages: list[str]) -> tuple[str, list[dict]]:
    """Grenzt Abschnitt 2 und die Jahrgangsbänder anhand ihrer Überschriften ab.

    Liefert (pk_text, [band, …]) mit band = {nummer, titel, klasse_von, klasse_bis, niveau, text}.
    Wirft ValueError, wenn die Struktur nicht erkannt wird.
    """
    pk_start = end = None
    bands: list[dict] = []  # {page, titel, von, bis, niveau}
    for i, page in enumerate(pages):
        for line in _page_top_lines(page):
            if len(line) >= 60:
                continue
            if pk_start is None and _PK_HEAD_RE.match(line):
                pk_start = i
                break
            m = _BAND_HEAD_RE.match(line)
            if m and pk_start is not None:
                grades = [int(x) for x in re.findall(r"\d+", m.group(1))]
                rest = m.group(2) or ""
                niveau = "leistung" if "Leistungsfach" in rest else ("basis" if "Basisfach" in rest else None)
                bands.append({
                    "page": i, "titel": line, "niveau": niveau,
                    "von": grades[0], "bis": grades[-1],
                })
                break
            if end is None and pk_start is not None and _END_HEAD_RE.match(line):
                end = i
                break
        if end is not None:
            break

    if pk_start is None or not bands:
        raise ValueError(
            "Fremdsprachen-Struktur nicht erkannt (Abschnitt 2 / Jahrgangsbänder nicht gefunden)."
        )
    if end is None:
        end = len(pages)

    pk_text = "\n".join(pages[pk_start:bands[0]["page"]])
    out: list[dict] = []
    for idx, b in enumerate(bands):
        stop = bands[idx + 1]["page"] if idx + 1 < len(bands) else end
        out.append({
            "nummer": f"3.{idx + 1}",
            "titel": b["titel"],
            "klasse_von": b["von"],
            "klasse_bis": b["bis"],
            "niveau": b["niveau"],
            "text": "\n".join(pages[b["page"]:stop]),
        })
    return pk_text, out


def extract_fremdsprache_chunked(
    pages: list[str],
    *,
    fach_titel: str,
    model: str = DEFAULT_MODEL,
    proxy_url: str | None = None,
    api_key: str | None = None,
    log=lambda msg: None,
) -> dict:
    """Band-weise Extraktion großer Fremdsprachen-PDFs → vollständige neutrale Struktur.

    `log` ist ein optionaler Callback für Fortschrittsmeldungen (z. B. print)."""
    proxy_url = (proxy_url or os.environ.get("LITELLM_PROXY_URL", "http://localhost:4000")).rstrip("/")
    api_key = api_key or os.environ.get("LITELLM_MASTER_KEY", "")

    pk_text, band_chunks = detect_fremdsprache_chunks(pages)
    log(f"Erkannt: Abschnitt 2 + {len(band_chunks)} Jahrgangsbänder")

    pk_data = _chat_completion_json(
        pk_text, system=_FS_PK_SYSTEM, model=model, proxy_url=proxy_url, api_key=api_key
    )
    pk_list = pk_data.get("prozessbezogene_kompetenzbereiche") or []
    log(f"  Abschnitt 2: {len(pk_list)} prozessbezogene Bereiche")

    jahrgangsstufen: list[dict] = []
    for band in band_chunks:
        data = _chat_completion_json(
            band["text"], system=_FS_BAND_SYSTEM, model=model, proxy_url=proxy_url, api_key=api_key
        )
        bereiche = data.get("kompetenzbereiche") or []
        jahrgangsstufen.append({
            "nummer": band["nummer"],
            "titel": band["titel"],
            "klasse_von": band["klasse_von"],
            "klasse_bis": band["klasse_bis"],
            "niveau": band["niveau"],
            "kompetenzbereiche": bereiche,
        })
        n_ik = sum(
            len(b.get("kompetenzen") or []) + sum(len(t.get("kompetenzen") or []) for t in (b.get("teilbereiche") or []))
            for b in bereiche
        )
        log(f"  {band['nummer']} {band['titel']}: {len(bereiche)} Bereiche, {n_ik} Kompetenzen")

    op_text = detect_operator_chunk(pages)
    operatoren: list[dict] = []
    if op_text:
        op_data = _chat_completion_json(
            op_text, system=_OPERATOR_SYSTEM, model=model, proxy_url=proxy_url, api_key=api_key
        )
        operatoren = op_data.get("operatoren") or []
        log(f"  Operatoren: {len(operatoren)}")

    structure = {
        "fach": {"titel": fach_titel, "leitgedanken": ""},
        "prozessbezogene_kompetenzbereiche": pk_list,
        "jahrgangsstufen": jahrgangsstufen,
        "operatoren": operatoren,
    }
    validate_fremdsprache_structure(structure)
    return structure
