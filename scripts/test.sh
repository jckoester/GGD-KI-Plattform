#!/usr/bin/env bash
#
# Führt alle automatischen Prüfungen des Projekts aus: Backend-Tests (Unit und
# Integration), Frontend-Tests, Svelte-Typprüfung und ESLint.
#
#   scripts/test.sh              alles (~40 s)
#   scripts/test.sh --schnell    ohne Integrationstests (ohne laufende PostgreSQL-Instanz)
#
# Der Rückgabewert ist nur dann 0, wenn jeder Schritt durchläuft. Dadurch ist das
# Skript als Git-Hook verwendbar — siehe .githooks/pre-push.
#
# Kein `set -e`: Es sollen *alle* Schritte laufen, auch wenn einer fehlschlägt.
# Ein Lauf, der beim ersten Fehler abbricht, verschweigt die übrigen.

set -uo pipefail

WURZEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WURZEL" || exit 2

SCHNELL=0
for arg in "$@"; do
  case "$arg" in
    --schnell|--quick) SCHNELL=1 ;;
    -h|--help)
      sed -n '3,11p' "$0" | sed 's/^#\{1,\} \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unbekannte Option: $arg (bekannt: --schnell)" >&2
      exit 2
      ;;
  esac
done

# Farben nur, wenn ein Terminal dranhängt — in einer Pipe stören die Steuerzeichen.
if [ -t 1 ]; then
  ROT=$'\033[31m'; GRUEN=$'\033[32m'; GELB=$'\033[33m'
  GRAU=$'\033[90m'; FETT=$'\033[1m'; AUS=$'\033[0m'
else
  ROT=''; GRUEN=''; GELB=''; GRAU=''; FETT=''; AUS=''
fi

PYTHON="$WURZEL/backend/venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "${ROT}Keine virtuelle Umgebung unter backend/venv.${AUS}" >&2
  echo "Anlegen: siehe docs/dev/dev-setup.md, Abschnitt „Backend“." >&2
  exit 2
fi
if [ ! -d "$WURZEL/frontend/node_modules" ]; then
  echo "${ROT}frontend/node_modules fehlt.${AUS}" >&2
  echo "Einmalig: cd frontend && npm install" >&2
  exit 2
fi

ANZAHL_FEHLER=0
NAMEN_FEHLER=""
LETZTES_LOG=""
BEGINN=$SECONDS

# schritt <Anzeigename> <Muster für die Kurzfassung> <Befehl>
#
# Bei Erfolg steht nur eine Zeile da; bei Fehlschlag die letzten 60 Zeilen der
# Ausgabe plus der Befehl zum Nachstellen. Der Vollausdruck jedes grünen Laufs
# wäre Rauschen, das man nach dem dritten Mal nicht mehr liest.
schritt() {
  local name="$1" muster="$2" befehl="$3"
  local log start dauer kurz
  log="$(mktemp)"
  printf '  %-22s' "$name"
  start=$SECONDS
  if bash -c "$befehl" >"$log" 2>&1; then
    dauer=$(( SECONDS - start ))
    kurz=""
    [ -n "$muster" ] && kurz="$(grep -Eo "$muster" "$log" 2>/dev/null | tail -1)"
    printf '%s✓%s %s %s(%ss)%s\n' "$GRUEN" "$AUS" "$kurz" "$GRAU" "$dauer" "$AUS"
    rm -f "$log"
    LETZTES_LOG=""
    return 0
  fi
  printf '%s✗%s\n' "$ROT" "$AUS"
  printf '%s' "$GRAU"
  # Fortschrittszeilen ("......F  [ 42%]") vor dem Abschneiden entfernen — sonst
  # bleibt von den letzten 60 Zeilen nichts als Punkte übrig.
  grep -Ev '^[.sfFEPuxX ]*\[ *[0-9]+%\]$' "$log" | tail -n 60 | sed 's/^/      /'
  printf '      Nachstellen: %s%s\n' "$befehl" "$AUS"
  ANZAHL_FEHLER=$(( ANZAHL_FEHLER + 1 ))
  NAMEN_FEHLER="$NAMEN_FEHLER · $name"
  LETZTES_LOG="$log"
  return 1
}

echo
echo "${FETT}Prüfung des Projekts${AUS} ${GRAU}(${WURZEL})${AUS}"
echo

# --disable-warnings und --tb=short sind für die Lesbarkeit im Fehlerfall da: Ohne sie
# füllen ~40 Zeilen Deprecation-Warnungen die Ausgabe, und der eine rote Test steht
# unter dem Rand. Die Warnungen sind dadurch nicht weg — `pytest tests/unit` zeigt sie
# unverändert.
PYTEST="venv/bin/python -m pytest -q --disable-warnings --tb=short"

echo "${FETT}Backend${AUS}"
schritt "Unit-Tests" '[0-9]+ (passed|failed).*' \
  "cd backend && $PYTEST tests/unit"

if [ "$SCHNELL" -eq 1 ]; then
  printf '  %-22s%s— übersprungen (--schnell)%s\n' "Integrationstests" "$GELB" "$AUS"
else
  if ! schritt "Integrationstests" '[0-9]+ (passed|failed).*' \
      "cd backend && $PYTEST tests/integration"; then
    # Eine nicht erreichbare Datenbank sieht im Traceback aus wie ein Testfehler.
    # Der Unterschied ist wichtig genug für einen eigenen Hinweis.
    if grep -qiE "TEST_DATABASE_URL|Connection refused|Connect call failed|could not connect|ConnectionRefused" \
        "$LETZTES_LOG" 2>/dev/null; then
      echo "      ${GELB}Hinweis:${AUS} Läuft PostgreSQL? Die Integrationstests brauchen eine"
      echo "      erreichbare Test-Datenbank (TEST_DATABASE_URL in .env, pgvector nötig)."
      echo "      Bewusst ohne sie prüfen: scripts/test.sh --schnell"
    fi
    rm -f "$LETZTES_LOG"
  fi
fi

echo
echo "${FETT}Frontend${AUS}"
schritt "Tests" 'Tests +[0-9]+ (passed|failed).*' \
  "cd frontend && npm run --silent test"
# Anzeigenamen bewusst ohne Umlaute: printf zählt für %-22s Bytes, nicht Zeichen —
# ein „ü“ verschöbe die Spalte um eine Stelle.
schritt "Typen (svelte-check)" 'COMPLETED.*' \
  "cd frontend && npm run --silent check"
schritt "Lint" '([0-9]+ problems.*)' \
  "cd frontend && npm run --silent lint"

# Kein eigener Schritt für das Taxonomie-Generat: Dass
# frontend/src/lib/taxonomy.js zu backend/app/context/taxonomy.yaml passt, prüft
# bereits test_taxonomy_check.py::TestFrontendAbleitung — und zwar besser, weil es
# nach tmp_path erzeugt und den Arbeitsbaum nicht anfasst. Eine zweite Umsetzung
# derselben Regel wäre genau die Doppelung, die hier ohnehin schon Ärger macht.

GESAMT=$(( SECONDS - BEGINN ))
echo
if [ "$ANZAHL_FEHLER" -eq 0 ]; then
  if [ "$SCHNELL" -eq 1 ]; then
    echo "${GRUEN}${FETT}Grün${AUS} ${GELB}(ohne Integrationstests)${AUS} ${GRAU}${GESAMT}s${AUS}"
  else
    echo "${GRUEN}${FETT}Alles grün${AUS} ${GRAU}${GESAMT}s${AUS}"
  fi
  exit 0
fi
echo "${ROT}${FETT}${ANZAHL_FEHLER} Schritt(e) fehlgeschlagen:${AUS}${NAMEN_FEHLER# ·} ${GRAU}${GESAMT}s${AUS}"
exit 1
