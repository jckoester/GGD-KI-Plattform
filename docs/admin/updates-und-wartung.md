# Updates & Wartung

## Reguläres Update

```bash
git pull
docker compose build --no-cache
docker compose up -d
docker compose exec backend alembic upgrade head
```

`alembic upgrade head` ist immer auszuführen — er ist idempotent und schadet
nicht, wenn keine neuen Migrationen vorliegen.

Nach dem Update die Plattform kurz im Browser prüfen und die Logs beobachten:

```bash
docker compose logs -f backend
```

## LiteLLM updaten

LiteLLM verwaltet sein eigenes Datenbankschema über Prisma. Ein einfaches
`pip install --upgrade litellm` genügt nicht — Schema und Prisma-Client müssen
separat nachgezogen werden, sonst kann es zu Fehlern wie
`'LiteLLM_TeamTable' object has no attribute '...'` kommen.

**Reihenfolge beim LiteLLM-Update:**

```bash
# 1. LiteLLM-Container neu bauen (zieht neue Version)
docker compose build --no-cache litellm
docker compose up -d litellm

# 2. DB-Schema aktualisieren
docker compose exec litellm prisma migrate deploy

# 3. Prisma-Python-Client neu generieren
docker compose exec litellm sh -c "
  LITELLM_DIR=\$(python3 -c 'import litellm, os; print(os.path.dirname(litellm.__file__))')
  cd \"\$LITELLM_DIR/proxy\"
  prisma generate --schema=schema.prisma
"

# 4. LiteLLM neu starten
docker compose restart litellm
```

## Datenbank-Backup

Ein tägliches Backup des PostgreSQL-Volumes wird empfohlen:

```bash
docker compose exec db pg_dump -U postgres ggd_ki > backup_$(date +%F).sql
```

Das Backup enthält alle Nutzerkonten, Konversationen und Budgetdaten.
`SCHOOL_SECRET` separat sichern — ohne ihn ist eine De-Anonymisierung
auch mit Backup nicht möglich.

---

## Schuljahreswechsel

### Was automatisch passiert

- **Abgänger** (kein Login > 90 Tage) werden automatisch gelöscht. Nach dem
  Schuljahresende sind Abgänger spätestens in den Herbstferien bereinigt.
- **Neue Schüler:innen** erhalten beim ersten Login automatisch ein Konto und
  werden anhand ihrer SSO-Jahrgangsgruppe der richtigen Budget-Klasse zugeordnet.
- **Jahrgangs­wechsel:** Wenn Schüler:innen im SSO-System in die nächste
  Jahrgangsgruppe verschoben werden, zieht das neue Budget beim nächsten
  Monats-Reconcile (1. des Monats) automatisch nach.

### Was manuell geprüft werden sollte

**Im SSO-System (nicht in der Plattform):**
- Wurden alle Schüler:innen in ihre neuen Jahrgangsgruppen verschoben?
- Sind Abgänger aus den Schulgruppen entfernt?

**In der Plattform:**
- `config/budget_tiers.yaml`: Sollen sich Budget-Beträge für bestimmte
  Jahrgänge ändern? Falls ja: Datei anpassen und Reconcile-Skript ausführen.
- `STUDENT_GRADES` in `.env`: Enthält die Liste noch alle relevanten Jahrgänge?
  (Relevant wenn ein neuer 5. Jahrgang hinzukommt oder der 12. endet.)
- Assistenten: Sind alle Assistenten noch aktuell und für das neue Schuljahr passend?

### Abgänger vor der automatischen Löschung bereinigen

Falls Schule oder Datenschutzbeauftragte eine frühere Löschung wünschen:

```bash
# Vorschau: zeigt an, welche Konten gelöscht würden
docker compose exec backend python scripts/cleanup_inactive_accounts.py --dry-run

# Zum Testen mit einem fiktiven "jetzt"-Datum (90 Tage nach Schuljahresende):
docker compose exec backend python scripts/cleanup_inactive_accounts.py \
  --now 2026-10-01T02:00:00+00:00 --dry-run

# Tatsächlich ausführen (ohne --dry-run):
docker compose exec backend python scripts/cleanup_inactive_accounts.py \
  --now 2026-10-01T02:00:00+00:00
```

---

## Log-Auswertung

```bash
docker compose logs -f backend     # Backend-Logs
docker compose logs -f cron        # Cron-Job-Ausgaben
docker compose logs -f litellm     # LiteLLM-Proxy-Logs
```

Häufige Meldungen und ihre Bedeutung:

| Meldung | Bedeutung | Handlungsbedarf |
|---------|----------|----------------|
| `429` von LiteLLM | Budget einer Nutzerin aufgebraucht | Normal, kein Handlungsbedarf |
| `Connection refused` zu LiteLLM | LiteLLM-Container nicht erreichbar | `LITELLM_PROXY_URL` in `.env` prüfen |
| `alembic.util.exc.CommandError` beim Start | Datenbank-Migration fehlt | `alembic upgrade head` ausführen |
| `SCHOOL_SECRET not set` | Pflichtumgebungsvariable fehlt | `config/.env` prüfen |

## Troubleshooting

**Nutzer:innen können sich nicht einloggen**
`config/auth.yaml` prüfen: Sind die Gruppen in `group_role_map` exakt so
geschrieben wie im SSO-System? Groß-/Kleinschreibung beachten.

**Nutzer:innen sehen keine Modelle**
Die Modell-Freischaltungsmatrix unter `/settings/models` ist noch leer.
Für jede Nutzergruppe mindestens ein Modell aktivieren.

**Budget wird nicht monatlich erneuert**
Prüfen ob der `cron`-Container läuft: `docker compose ps cron`.
Cron-Log prüfen: `docker compose logs cron`. Bei Bedarf Skripte manuell
ausführen (siehe [Budget-System](budget.md)).

**Pseudonyme haben sich geändert**
`SCHOOL_SECRET` wurde in `config/.env` geändert. Dieser Vorgang ist nicht
reversibel — alle bestehenden Nutzerzuordnungen sind ungültig.
Backup einspielen und `SCHOOL_SECRET` auf den ursprünglichen Wert zurücksetzen.
