#!/usr/bin/env python3
"""
Fragt den IONOS AI Model Hub ab — Vorarbeit für die LiteLLM-Config (IONOS-Plan, Schritt 9).

**Diagnosewerkzeug, kein Produktcode.** Es liest und berichtet; geschrieben wird nichts.
Gedacht für den Lauf, sobald der Zugang steht, und für eine Wiederholung, wenn IONOS den
Katalog ändert (Modelle werden dort abgekündigt, siehe Doku „Retirement").

Die Vorlage `infra/litellm_config.ionos.example.yaml` hat rund 30 Stellen mit `<…>`/`TODO`.
Vier davon lassen sich nicht erraten und auch nicht der Doku entnehmen — sie stehen nur in
der laufenden API. Genau die beantwortet dieser Lauf:

  A  Welche Modell-IDs gibt es? → `model:` je Eintrag (`openai/<id>`)
  B  Beherrscht das Chat-Modell Function-Calling? → `supports_function_calling`
     PFLICHT: Ohne diese Fähigkeit fallen sämtliche Werkzeuge (Wissensgraph,
     Unterrichtsplanung, Bildgenerierung) **stumm** aus — das Modell antwortet, ruft aber nie
     ein Tool. Der Fehler sieht aus wie ein schlechtes Modell, nicht wie ein Konfigurationsfehler.
  C  Wie breit ist der Embedding-Vektor? → `EMBEDDING_DIMENSIONS` + Migration/Re-Embedding.
     Weicht der Wert von der Spaltenbreite ab, bricht `generate_embedding()` mit
     `EmbeddingDimensionError`; der Weg dahin steht in `docs/runbooks/modellwechsel.md`.
  D  Liefert das Bildmodell Base64 oder eine URL? → `IMAGE_RESPONSE_FORMAT`.
     Eine URL ist an dieser Stelle ein Datenschutzproblem (das Bild läge beim Anbieter und
     würde vom Browser der Schüler:in direkt dort geladen); `chat/router.py` bricht deshalb
     bewusst mit einem `RuntimeError` ab.

Was der Lauf NICHT beantwortet: die **Preise**. Die stehen in der IONOS-Preisliste, nicht in
der API. Ohne `input_cost_per_token`/`output_cost_per_token` in der LiteLLM-Config bleibt der
SpendLog bei 0 — und damit sind EUR-Budgets, 429-Sperre und Kostenstatistik wirkungslos,
ohne dass irgendetwas fehlschlägt.

Zugang — **niemals** in diese Datei schreiben. Der Token kommt aus der Umgebung oder aus der
`.env` im Repo-Wurzelverzeichnis (die liest das Skript selbst, wenn die Variable fehlt):

    IONOS_API_KEY=<token aus dem Data Center Designer → Token Manager>
    IONOS_API_BASE=https://openai.inference.de-txl.ionos.com/v1

Verwendung:

    python scripts/ionos_probe.py                        # nur der Katalog (A)
    python scripts/ionos_probe.py --chat <id>            # + Chat und Function-Calling (B)
    python scripts/ionos_probe.py --embedding <id>       # + Vektorbreite (C)
    python scripts/ionos_probe.py --image <id>           # + Base64 oder URL (D)

Der Katalog kostet nichts. Die drei Tests schicken je eine winzige Anfrage — der Bildtest
erzeugt ein echtes Bild und kostet entsprechend.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

WURZEL = Path(__file__).resolve().parent.parent
STANDARD_BASE = "https://openai.inference.de-txl.ionos.com/v1"
TIMEOUT = httpx.Timeout(120.0, connect=15.0)


# ── Zugang ──────────────────────────────────────────────────────────────────────────


def _aus_env_datei(name: str) -> str | None:
    """Liest einen Wert aus der `.env` im Repo-Wurzelverzeichnis (nur wenn nötig)."""
    pfad = WURZEL / ".env"
    if not pfad.is_file():
        return None
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        schluessel, _, wert = zeile.partition("=")
        if schluessel.strip() == name:
            return wert.strip().strip("'\"") or None
    return None


def _zugang() -> tuple[str, str]:
    token = os.environ.get("IONOS_API_KEY") or _aus_env_datei("IONOS_API_KEY")
    if not token:
        sys.exit(
            "FEHLER: IONOS_API_KEY fehlt — weder in der Umgebung noch in der .env.\n"
            "Token im IONOS Data Center Designer erzeugen (Token Manager) und in die .env "
            "eintragen."
        )
    base = (
        os.environ.get("IONOS_API_BASE")
        or _aus_env_datei("IONOS_API_BASE")
        or STANDARD_BASE
    )
    return token, base.rstrip("/")


def _client(token: str, base: str) -> httpx.Client:
    return httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )


def _fehler(antwort: httpx.Response) -> str:
    """Fehlertext ohne Token — die Antwort spiegelt Header nicht, der Body kann alles sein."""
    text = antwort.text.strip()
    return f"HTTP {antwort.status_code}: {text[:400] or '(leerer Body)'}"


# ── A — Katalog ─────────────────────────────────────────────────────────────────────


def katalog(client: httpx.Client) -> list[dict]:
    print("── A  Katalog (GET /models) ────────────────────────────────────────────────")
    try:
        antwort = client.get("/models")
    except httpx.HTTPError as e:
        sys.exit(f"FEHLER: {base_hinweis(e)}")
    if antwort.status_code == 401:
        sys.exit(f"FEHLER: Token abgelehnt. {_fehler(antwort)}")
    if antwort.status_code != 200:
        sys.exit(f"FEHLER: {_fehler(antwort)}")

    modelle = antwort.json().get("data", [])
    if not modelle:
        print("  Keine Modelle — Zugang steht, aber der Katalog ist leer.")
        return []

    print(f"  {len(modelle)} Modelle:\n")
    for m in sorted(modelle, key=lambda m: str(m.get("id", ""))):
        # Neben `id` führt IONOS je nach Modell weitere Felder. Alles Unbekannte mitzeigen,
        # statt eine feste Feldliste zu raten — der Katalog ändert sich.
        extra = {
            k: v for k, v in m.items() if k not in {"id", "object", "created", "owned_by"}
        }
        zusatz = f"   {json.dumps(extra, ensure_ascii=False)}" if extra else ""
        print(f"  · {m.get('id')}{zusatz}")
    print()
    return modelle


def base_hinweis(e: httpx.HTTPError) -> str:
    return f"{type(e).__name__}: {e} — stimmt IONOS_API_BASE?"


# ── B — Chat und Function-Calling ───────────────────────────────────────────────────

_WERKZEUG = {
    "type": "function",
    "function": {
        "name": "gib_note",
        "description": "Gibt die Note für eine Klassenarbeit zurück.",
        "parameters": {
            "type": "object",
            "properties": {"punkte": {"type": "integer"}},
            "required": ["punkte"],
        },
    },
}


def chat(client: httpx.Client, modell: str) -> None:
    print(f"── B  Chat + Function-Calling ({modell}) ───────────────────────────────────")

    antwort = client.post(
        "/chat/completions",
        json={
            "model": modell,
            "messages": [{"role": "user", "content": "Antworte mit genau einem Wort: Ditzingen"}],
            # Großzügig: Reasoning-Modelle verbrauchen ihr Budget zuerst für die Denkspur und
            # liefern `content: null`, wenn vorher `length` erreicht ist. Ein knappes Limit
            # sähe hier wie ein kaputtes Modell aus.
            "max_tokens": 512,
        },
    )
    if antwort.status_code != 200:
        print(f"  Chat FEHLGESCHLAGEN — {_fehler(antwort)}\n")
        return
    daten = antwort.json()
    wahl = (daten.get("choices") or [{}])[0]
    nachricht = wahl.get("message") or {}
    inhalt = (nachricht.get("content") or "").strip()
    grund = wahl.get("finish_reason")
    if inhalt:
        print(f"  Chat OK — Antwort: {inhalt[:80]!r}  (finish_reason: {grund})")
    else:
        print(f"  Chat: LEERER content (finish_reason: {grund})")
    # Reasoning-Modelle legen die Denkspur in ein eigenes Feld (`reasoning`; manche Anbieter
    # nennen es `reasoning_content`). Das Backend zeigt nur `content` — ein Modell, das sein
    # Token-Budget in der Denkspur verbraucht, wirkt im Chat stumm und kostet trotzdem.
    denkspur = nachricht.get("reasoning") or nachricht.get("reasoning_content")
    if denkspur:
        print(f"  Denkspur: {len(denkspur)} Zeichen — Reasoning-Modell")
    if nutzung := daten.get("usage"):
        print(f"  usage: {json.dumps(nutzung, ensure_ascii=False)}")

    # Der eigentliche Prüfpunkt: Ein Modell ohne Tool-Unterstützung antwortet hier freundlich
    # in Prosa, statt `tool_calls` zu liefern — und genau so fällt es später im Betrieb aus.
    antwort = client.post(
        "/chat/completions",
        json={
            "model": modell,
            "messages": [
                {"role": "user", "content": "Wie lautet die Note bei 12 Punkten? Nutze das Werkzeug."}
            ],
            "tools": [_WERKZEUG],
            "tool_choice": "auto",
            "max_tokens": 512,
        },
    )
    if antwort.status_code != 200:
        print(f"  Function-Calling NICHT nutzbar — {_fehler(antwort)}")
        print("  → supports_function_calling: false; Werkzeuge fallen mit diesem Modell aus.\n")
        return
    nachricht = (antwort.json().get("choices") or [{}])[0].get("message", {})
    if aufrufe := nachricht.get("tool_calls"):
        namen = ", ".join(a.get("function", {}).get("name", "?") for a in aufrufe)
        print(f"  Function-Calling OK — tool_calls: {namen}")
        print("  → supports_function_calling: true\n")
    else:
        print("  Function-Calling: KEIN tool_calls, nur Prosa —")
        print(f"     {str(nachricht.get('content'))[:120]!r}")
        print("  → Für Chat-Stufen mit Werkzeugen ungeeignet.\n")


# ── C — Embedding-Breite ────────────────────────────────────────────────────────────


def embedding(client: httpx.Client, modell: str) -> None:
    print(f"── C  Embedding-Breite ({modell}) ──────────────────────────────────────────")
    antwort = client.post(
        "/embeddings",
        json={"model": modell, "input": "Die Schülerin beschreibt den Wasserkreislauf."},
    )
    if antwort.status_code != 200:
        print(f"  FEHLGESCHLAGEN — {_fehler(antwort)}\n")
        return
    vektoren = antwort.json().get("data") or []
    if not vektoren:
        print("  Antwort ohne `data` — unerwartetes Format.\n")
        return
    breite = len(vektoren[0].get("embedding") or [])
    print(f"  OK — {breite} Dimensionen")
    print(f"  → EMBEDDING_DIMENSIONS={breite}")
    if breite != 1536:
        print(
            "  ⚠️ Weicht von der heutigen Spaltenbreite (1536) ab: Spalte umstellen UND alles\n"
            "     neu einbetten — docs/runbooks/modellwechsel.md."
        )
    print()


# ── D — Bild: Base64 oder URL ───────────────────────────────────────────────────────


def bild(client: httpx.Client, modell: str) -> None:
    print(f"── D  Bildformat ({modell}) ────────────────────────────────────────────────")
    print("  (erzeugt ein echtes Bild — kostet)")
    antwort = client.post(
        "/images/generations",
        json={"model": modell, "prompt": "Ein einfacher blauer Kreis auf weißem Grund", "n": 1},
    )
    if antwort.status_code != 200:
        print(f"  FEHLGESCHLAGEN — {_fehler(antwort)}\n")
        return
    eintraege = antwort.json().get("data") or []
    if not eintraege:
        print("  Antwort ohne `data` — unerwartetes Format.\n")
        return
    eintrag = eintraege[0]
    if eintrag.get("b64_json"):
        print(f"  OK — Base64 ({len(eintrag['b64_json'])} Zeichen), ohne Parameter")
        print("  → IMAGE_RESPONSE_FORMAT leer lassen")
    elif eintrag.get("url"):
        print("  URL statt Base64 —")
        print("  → IMAGE_RESPONSE_FORMAT=b64_json setzen und erneut prüfen; sonst bricht die")
        print("     Bildgenerierung bewusst mit RuntimeError ab (Datenschutzgrenze).")
    else:
        print(f"  Weder b64_json noch url: {list(eintrag)}")
    print()


# ── Ablauf ──────────────────────────────────────────────────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(
        description="Fragt den IONOS AI Model Hub ab (Katalog, Function-Calling, "
        "Embedding-Breite, Bildformat).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--chat", metavar="ID", help="Chat- und Function-Calling-Test mit dieser Modell-ID")
    p.add_argument("--embedding", metavar="ID", help="Embedding-Test — misst die Vektorbreite")
    p.add_argument("--image", metavar="ID", help="Bildtest — Base64 oder URL (kostet)")
    p.add_argument("--katalog", action="store_true", help="Katalog auch neben den Tests zeigen")
    args = p.parse_args()

    tests = bool(args.chat or args.embedding or args.image)
    token, base = _zugang()
    print(f"\nIONOS AI Model Hub — {base}\n")

    with _client(token, base) as client:
        # Beim Prüfen einzelner Modelle (oft in einer Schleife) wäre der Katalog nur Lärm.
        if args.katalog or not tests:
            katalog(client)
        if args.chat:
            chat(client, args.chat)
        if args.embedding:
            embedding(client, args.embedding)
        if args.image:
            bild(client, args.image)

    if not tests:
        print(
            "Weiter: eine Modell-ID je Modalität wählen und prüfen —\n"
            "  python scripts/ionos_probe.py --chat <id> --embedding <id>\n"
        )


if __name__ == "__main__":
    main()
