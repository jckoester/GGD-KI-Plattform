# Budget-System

## Konzept

Jede Nutzerin und jeder Nutzer hat ein monatliches Budget in Euro. Günstigere
Modelle verbrauchen das Budget langsamer; leistungsstärkere schneller.

Intern arbeitet LiteLLM mit US-Dollar. Das Backend holt monatlich den aktuellen
EUR→USD-Wechselkurs von der Europäischen Zentralbank (ECB) und berechnet daraus
die USD-Limits, die LiteLLM als harte Grenzen durchsetzt. Überschreitungen werden
mit HTTP 429 abgelehnt — die Plattform zeigt Nutzer:innen dann eine verständliche
Fehlermeldung.

## Budget-Tiers konfigurieren

Die Datei `config/budget_tiers.yaml` legt fest, wie viel Budget welcher Gruppe
pro Monat zusteht:

```yaml
grades:
  5:
    budget_duration: 1mo
    max_budget_eur: 1.00
  10:
    budget_duration: 1mo
    max_budget_eur: 2.00
  12:
    budget_duration: 1mo
    max_budget_eur: 3.50

roles:
  teacher:
    budget_duration: 1mo
    max_budget_eur: 8.00
```

- `grades` gilt für Schüler:innen und wird über den Jahrgang zugeordnet.
- `roles` gilt für alle anderen Rollen (z. B. `teacher`, `admin`).
- Hat eine Schülerin sowohl einen Jahrgangs- als auch einen Rollen-Eintrag,
  hat der Jahrgangs-Eintrag Vorrang.

Änderungen an der Datei werden **nicht sofort wirksam** — sie greifen erst
beim nächsten Monats-Reconcile (1. des Monats). Um Änderungen sofort anzuwenden:

```bash
docker compose exec backend python scripts/monthly_budget_reconcile.py
```

## Cron-Jobs

Zwei automatische Jobs sorgen dafür, dass Budgets korrekt verwaltet werden:

| Job | Zeitplan | Beschreibung |
|-----|---------|-------------|
| ECB-Wechselkurs abrufen | 1. des Monats, 06:00 Uhr | Holt den aktuellen EUR→USD-Kurs |
| Budget-Reconcile | 1. des Monats, 07:00 Uhr | Berechnet USD-Limits neu und setzt sie in LiteLLM |

Bei Bedarf manuell ausführen:

```bash
docker compose exec backend python scripts/refresh_ecb_rate.py
docker compose exec backend python scripts/monthly_budget_reconcile.py
```

## Admin-Übersicht (`/budget`)

Im Admin-Bereich zeigt `/budget` eine aggregierte Übersicht der Ausgaben —
aufgeschlüsselt nach Nutzergruppen und Jahrgängen. Die Anzeige ist
pseudonymisiert: es sind keine Klarnamen sichtbar.

Für rechtlich begründete Einzelfälle (z. B. Missbrauchsverdacht) ist eine
De-Anonymisierung über das Audit-Log möglich — dies wird protokolliert.
Details dazu in [Datenschutz & Betrieb](datenschutz-betrieb.md).
