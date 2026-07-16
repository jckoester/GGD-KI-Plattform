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


def _chat_completion_json(
    text: str,
    *,
    system: str,
    model: str,
    proxy_url: str,
    api_key: str,
    timeout: float = 300.0,
) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    resp = httpx.post(
        f"{proxy_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Modell lieferte kein gültiges JSON: {exc}") from exc


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
