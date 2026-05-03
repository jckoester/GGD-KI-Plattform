# Update-Guide

Hinweise und Fallstricke beim Aktualisieren der Plattform-Komponenten.

---

## Modell-Freischaltung (Admin-Matrix)

### Leere Matrix = kein Modellzugriff

Solange die Modell-Freischaltungsmatrix leer ist, können Nutzer:innen keine Anfragen stellen.

**Empfohlene Vorgehensweise nach dem Ersteinrichten:**

1. Als Admin `/settings/models` aufrufen.
2. Für jede Gruppe mindestens ein Modell aktivieren.
3. Speichern.

> **Hinweis:** Das gewünschte Verhalten (leere Matrix = kein Zugriff) ist noch nicht vollständig implementiert — siehe Todo. Bis zur Korrektur gilt: Matrix nach Ersteinrichtung immer explizit befüllen.

---

## LiteLLM

### Nach jedem LiteLLM-Update

LiteLLM verwaltet sein DB-Schema über Prisma. Ein `pip install --upgrade litellm` aktualisiert nur den Python-Code — DB-Schema und Prisma-Client müssen separat nachgezogen werden. Fehlt einer der Schritte, können Fehler wie `'LiteLLM_TeamTable' object has no attribute '...'` auftreten, obwohl die Spalte in der DB existiert.

**Reihenfolge:**

```bash
# 1. DB-Schema aktualisieren
prisma migrate deploy

# 2. Prisma-Python-Client neu generieren
LITELLM_DIR=$(python3 -c "import litellm; import os; print(os.path.dirname(litellm.__file__))")
cd "$LITELLM_DIR/proxy"
prisma generate --schema=schema.prisma

# 3. LiteLLM neu starten
systemctl restart litellm
```

**Hintergrund:** LiteLLM hat zwei getrennte Repräsentationen seiner DB-Modelle — Pydantic-Typdefinitionen (`proxy/_types.py`) und einen Prisma-generierten DB-Client. `migrate deploy` aktualisiert die DB; `prisma generate` aktualisiert den generierten Client-Code. Beide müssen zum laufenden Python-Paket passen.

**Diagnose bei Attribut-Fehlern:**

```bash
# Prüfen ob das Pydantic-Modell das Feld kennt
python3 -c "from litellm.proxy._types import LiteLLM_TeamTable; print(LiteLLM_TeamTable.model_fields.keys())"

# Prüfen ob die Spalte in der DB existiert
psql -U <user> -d <db> \
  -c "SELECT column_name FROM information_schema.columns WHERE table_name = 'LiteLLM_TeamTable';"
```

Wenn das Pydantic-Modell das Feld kennt, die DB die Spalte hat, aber der Fehler trotzdem auftritt → `prisma generate` wurde nach dem letzten Update nicht ausgeführt.
