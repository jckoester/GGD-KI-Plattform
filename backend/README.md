# Backend Notes

## Cron-Jobs für Schritt 5d

Die Datenlöschung wird extern über Cron (oder systemd timer) angestoßen.

Beispiel:

```cron
0 2 * * * cd /Users/jan/Documents/1\ Projekte/GGD-KI-Plattform/backend && ./venv/bin/python scripts/cleanup_inactive_accounts.py
30 2 * * * cd /Users/jan/Documents/1\ Projekte/GGD-KI-Plattform/backend && ./venv/bin/python scripts/cleanup_stale_conversations.py
```

Dry-Run:

```bash
./venv/bin/python scripts/cleanup_inactive_accounts.py --dry-run
./venv/bin/python scripts/cleanup_stale_conversations.py --dry-run
```
