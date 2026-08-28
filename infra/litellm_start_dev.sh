#!/usr/bin/env bash
#
# Startet den lokalen LiteLLM-Proxy für die Entwicklung.
# Sourced .env aus dem Repo-Root, aktiviert die backend-venv und startet den
# Proxy auf Port 4000. Siehe docs/dev/dev-setup.md → "LiteLLM lokal starten".
#
# Nutzung (aus beliebigem Verzeichnis):
#   ./infra/litellm_start_dev.sh            # Port 4000, infra/litellm_config.dev.yaml
#   PORT=4001 ./infra/litellm_start_dev.sh  # anderer Port
#   CONFIG=infra/foo.yaml ./infra/litellm_start_dev.sh
set -euo pipefail

# Repo-Root = eine Ebene über diesem Skript (infra/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

PORT="${PORT:-4000}"
CONFIG="${CONFIG:-infra/litellm_config.dev.yaml}"
ENV_FILE="${ENV_FILE:-.env}"

# --- .env laden ---------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
  echo "FEHLER: $ENV_FILE nicht gefunden. Aus .env.example anlegen." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# --- Config prüfen ------------------------------------------------------------
if [[ ! -f "$CONFIG" ]]; then
  echo "FEHLER: Config $CONFIG fehlt." >&2
  echo "Anlegen mit: cp infra/litellm_config.dev.example.yaml $CONFIG" >&2
  exit 1
fi

# --- Pflicht-Variablen prüfen -------------------------------------------------
# Die Anbieter-Schlüssel NICHT fest verdrahten: Welche gebraucht werden, steht in der
# gewählten Config (`os.environ/NAME`). Ein fest geprüftes OPENAI_API_KEY würde den reinen
# IONOS-Betrieb blockieren — und ein fehlendes IONOS_API_KEY unbemerkt durchlassen.
missing=()
[[ -z "${LITELLM_MASTER_KEY:-}"   ]] && missing+=("LITELLM_MASTER_KEY")
[[ -z "${LITELLM_DATABASE_URL:-}" ]] && missing+=("LITELLM_DATABASE_URL")

while read -r var; do
  [[ -z "${!var:-}" ]] && missing+=("$var (von $CONFIG referenziert)")
done < <(grep -oE 'os\.environ/[A-Z0-9_]+' "$CONFIG" | cut -d/ -f2 | sort -u)

if (( ${#missing[@]} > 0 )); then
  echo "FEHLER: Diese Variablen fehlen in $ENV_FILE:" >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

# --- dedizierte Proxy-venv aktivieren (falls nicht schon aktiv) ---------------
# NICHT die backend-venv (Python 3.14) — dort scheitert der Proxy-Build.
LITELLM_VENV="${LITELLM_VENV:-infra/litellm-venv}"
if [[ -z "${VIRTUAL_ENV:-}" && -f "$LITELLM_VENV/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$LITELLM_VENV/bin/activate"
fi

if ! command -v litellm >/dev/null 2>&1; then
  echo "FEHLER: 'litellm' nicht gefunden. Dedizierte Proxy-venv (Python 3.13) anlegen:" >&2
  echo "  python3.13 -m venv $LITELLM_VENV" >&2
  echo "  source $LITELLM_VENV/bin/activate && pip install -r infra/litellm-requirements.txt" >&2
  exit 1
fi

# prisma-Modul vorhanden? (LiteLLM braucht es für die DB; hängt am Extra extra-proxy)
if ! python -c "import prisma" >/dev/null 2>&1; then
  echo "FEHLER: Python-Modul 'prisma' fehlt (nötig für den DB-gestützten Proxy)." >&2
  echo "  pip install -r infra/litellm-requirements.txt" >&2
  exit 1
fi

# Prisma-Client generieren, falls noch nicht vorhanden. `prisma generate` ohne
# --schema sucht im CWD und findet LiteLLMs Schema NICHT — es liegt im Paket
# (litellm/proxy/schema.prisma). Pfad dynamisch auflösen (versionsunabhängig).
if ! python -c "from prisma import Prisma" >/dev/null 2>&1; then
  echo "Prisma-Client wird generiert (LiteLLM-Schema)…"
  SCHEMA="$(python -c "import litellm, os; print(os.path.join(os.path.dirname(litellm.__file__), 'proxy', 'schema.prisma'))")"
  prisma generate --schema="$SCHEMA"
fi

# --- aus infra/ starten -------------------------------------------------------
# LiteLLM löst Guardrail-Module (`guardrails.llm_moderation.…`) und Pattern-Dateien als
# Pfade relativ zum ARBEITSVERZEICHNIS auf. Von der Repo-Wurzel aus greifen beide ins
# Leere; `infra/` entspricht zugleich dem Layout im Produktionscontainer.
# PYTHONPATH zusätzlich, weil llm_moderation.py `from moderation_core import …` nutzt.
CONFIG_ABS="$(cd "$(dirname "$CONFIG")" && pwd)/$(basename "$CONFIG")"
export PYTHONPATH="$ROOT_DIR/infra/guardrails${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT_DIR/infra"

echo "Starte LiteLLM-Proxy auf http://localhost:$PORT  (Config: $CONFIG)"
exec litellm --config "$CONFIG_ABS" --port "$PORT"
