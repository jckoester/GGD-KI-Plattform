#!/bin/sh
#
# Legt die zweite Datenbank an, in der der LiteLLM-Proxy sein Prisma-Schema führt
# (Virtual Keys, Teams, Budgets, SpendLogs). Sie muss von der Anwendungsdatenbank
# getrennt sein — Prisma und Alembic verwalten sonst dieselben Namensräume.
#
# ⚠️ Der Postgres-Entrypoint führt dieses Verzeichnis NUR bei leerem Datenverzeichnis
# aus, also bei einer Neuinstallation. Wer eine bestehende Installation umstellt, legt
# die Datenbank einmalig selbst an:
#
#     docker compose exec db psql -U postgres -c "CREATE DATABASE litellm"
#
# Prisma migriert in eine vorhandene Datenbank; anlegen kann es sie nicht. Fehlt sie,
# startet der Proxy nicht und der Container läuft in eine Neustartschleife.
set -e

# Der Name kommt aus derselben Quelle wie die Adresse, die der Proxy später benutzt —
# sonst legt das Skript eine Datenbank an, die niemand verwendet. Letztes Pfadsegment
# der URL, Query-String abgeschnitten.
DB_NAME="$(printf '%s' "${LITELLM_DATABASE_URL:-}" | sed -e 's#?.*##' -e 's#.*/##')"
[ -n "$DB_NAME" ] || DB_NAME="litellm"

# Ein Bezeichner, kein beliebiger Text: Der Name geht ungequotet in ein CREATE DATABASE.
case "$DB_NAME" in
  *[!A-Za-z0-9_]* | [!A-Za-z_]*)
    echo "FEHLER: '$DB_NAME' ist kein gültiger Datenbankname (aus LITELLM_DATABASE_URL)." >&2
    echo "Erwartet wird eine URL der Form postgresql://user:passwort@db:5432/litellm" >&2
    exit 1
    ;;
esac

echo "Lege Datenbank '$DB_NAME' für den LiteLLM-Proxy an (falls nicht vorhanden)…"

# `\gexec` führt das Ergebnis der Abfrage als Befehl aus — CREATE DATABASE kennt kein
# IF NOT EXISTS. Wiederholte Läufe bleiben damit folgenlos.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
SELECT 'CREATE DATABASE $DB_NAME'
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
EOSQL
