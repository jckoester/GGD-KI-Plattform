#!/usr/bin/env bash
# Mistral-Messung (Plan `Plaene/Mistral-Messung-Plan.md`, F1–F6 entschieden 17.11.2026).
#
#   scripts/mistral_messung.sh 1    # chat-komplex gegen mistral-large: vier Schüler-Assistenten
#   scripts/mistral_messung.sh 2    # chat-standard gegen mistral-small und ionos-qwen3.8-27b
#
# Aus `backend/`. Vorher (siehe Plan, Schritte 2–3):
#   - LiteLLM mit der Dev-Konfiguration neu gestartet (Alias `ionos-qwen3.8-27b`),
#   - `scripts/messung_freigabe.py setzen mistral-large mistral-small ionos-qwen3.8-27b`,
#     danach 5 Minuten warten (Backend-Cache) oder Backend neu starten,
#   - Budget der Messkonten (Schüler:innen-Konto, Lehrkraft 33) aufgebucht.
# Danach: `scripts/messung_freigabe.py zuruecknehmen`.
#
# Ein Lauf je Fall bei den Schüler-Assistenten, drei beim Stundenassistenten (F4). Jedes Modell
# frisch gemessen; die Verläufe tragen Kosten und Antwortzeiten.
set -euo pipefail
cd "$(dirname "$0")/.."

ZIEL="${ZIEL:-/Users/jan/Documents/PKM/Projekte/Konzeption GGD KI Client/Plaene/Messungen-Mistral}"
PY="venv/bin/python"
mkdir -p "$ZIEL"

phase="${1:-}"
case "$phase" in
  1)
    for modell in chat-komplex mistral-large; do
      for szenario in stoechiometrie mathe_aufgaben argumentieren lernen; do
        echo "== Phase 1: $szenario mit $modell"
        "$PY" scripts/assistent_messung.py --szenarien "scripts/szenarien/$szenario.yaml" \
          --modell "$modell" --lauf "p1-$szenario-$modell" --ziel "$ZIEL" \
          > "$ZIEL/p1-$szenario-$modell.log" 2>&1 || echo "   ✗ abgebrochen, siehe $ZIEL/p1-$szenario-$modell.log"
        tail -3 "$ZIEL/p1-$szenario-$modell.log"
      done
    done
    ;;
  2)
    for modell in chat-standard mistral-small ionos-qwen3.8-27b; do
      for datei in stundenentwurf stunde_finden; do
        echo "== Phase 2: Stundenassistent $datei mit $modell"
        "$PY" scripts/stundenassistent_messung.py --datei "scripts/szenarien/$datei.yaml" \
          --modell "$modell" --laeufe 3 \
          --verlauf "$ZIEL/p2-$datei-$modell.md" --json "$ZIEL/p2-$datei-$modell.json" \
          > "$ZIEL/p2-$datei-$modell.log" 2>&1 || echo "   ✗ abgebrochen, siehe $ZIEL/p2-$datei-$modell.log"
        tail -4 "$ZIEL/p2-$datei-$modell.log"
      done
      echo "== Phase 2: freier Chat (Rollenbehauptung) mit $modell"
      "$PY" scripts/assistent_messung.py --szenarien scripts/szenarien/rollenbehauptung.yaml \
        --vorlage frei --modell "$modell" --lauf "p2-frei-$modell" --ziel "$ZIEL" \
        > "$ZIEL/p2-frei-$modell.log" 2>&1 || echo "   ✗ abgebrochen, siehe $ZIEL/p2-frei-$modell.log"
      tail -3 "$ZIEL/p2-frei-$modell.log"
    done
    ;;
  *)
    echo "Aufruf: scripts/mistral_messung.sh 1|2" >&2
    exit 2
    ;;
esac
