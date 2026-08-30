# Runbook: Schuljahreswechsel

**Wann:** in den Sommerferien, vor dem ersten Unterrichtstag.
**Dauer:** etwa 30 Minuten, davon das meiste Prüfen.
**Risiko:** gering — aber ein Fehler hier trägt **das ganze Schuljahr** durch, weil die
Zahl der Unterrichtswochen die Jahreszusage bestimmt.

---

## Was von allein passiert

- **Budget-Rücksetzung.** Sobald `school_year.yaml` das neue Jahr führt, setzt der erste
  Zuteilungslauf Obergrenze **und** Verbrauch zurück. Kein eigener Lauf nötig, kein
  Datenbankeingriff. Reste des Vorjahres wandern **nicht** mit.
- **Abgänger** werden nach 90 Tagen ohne Login gelöscht (spätestens in den Herbstferien).
- **Neue Schüler:innen** bekommen beim ersten Login ein Konto und den Wochenbetrag ihres
  Jahrgangs.
- **Jahrgangswechsel** greift beim nächsten Zuteilungslauf, sobald das SSO-System die
  Person in die neue Gruppe verschoben hat.

## Was zu tun ist

### 1. `config/school_year.yaml` umstellen

Beginn, Ende, Halbjahreswechsel, Ferien, Feiertage, bewegliche Ferientage.

Der Ferienimport nimmt Arbeit ab (`/settings` → Ferien übernehmen). Er **ergänzt und
ersetzt nicht**: Von der Schule selbst gelegte Tage (Reisewoche, letzter Schultag) stehen
in keinem Ferienkalender und würden sonst verschwinden.

### 2. ⚠️ Die Zahl der Unterrichtswochen prüfen

**Der wichtigste Schritt.** Auf `/budget` steht sie unter der Stufentabelle:

> Dieses Schuljahr hat **40 Unterrichtswochen** (aus `school_year.yaml`).

Plausibilität: Ein volles Schuljahr hat grob 37–41 Unterrichtswochen. Kommt eine deutlich
größere Zahl heraus, fehlt ein Ferienzeitraum — und dann liegt die Jahressumme über dem,
was die Schule zugesagt hat.

Warum gerade hier: Die Zuteilung ist `Wochenbetrag × Unterrichtswochen`. Ein vergessener
Ferienzeitraum erzeugt zusätzliche Wochen; jede davon kostet einen vollen Wochenbetrag für
**alle** Nutzer:innen. Ein vergessener einzelner Feiertag ist dagegen folgenlos, solange
die Woche noch Unterricht hat.

### 3. Wochenbeträge prüfen

Auf `/budget`. Die Spalte **„Max-Kosten je Schuljahr"** ist die Zusage — sie muss zu dem
passen, was der Haushalt hergibt.

Grundlage für die Entscheidung ist die **Hochrechnung des Vorjahres**: Lag die Auslastung
bei 30 %, waren die Beträge zu niedrig angesetzt oder der Nutzerkreis zu klein. Beides
lässt sich jetzt korrigieren, im laufenden Jahr nur mühsam.

### 4. Nutzerkreis und Jahrgänge

- Im SSO-System: Sind alle in ihre neuen Jahrgangsgruppen verschoben? Abgänger entfernt?
- `PUBLIC_STUDENT_GRADES` in der `.env`: noch vollständig? (Relevant, wenn ein neuer
  Jahrgang 5 dazukommt oder die 12 ausläuft.)
- Ist der Zugang zur Plattform noch für den richtigen Personenkreis freigegeben? Das
  entscheidet der Auth-Provider, nicht die Plattform.

### 5. Ersten Zuteilungslauf prüfen

Nicht auf den Montag warten, sondern trocken vorab:

```bash
docker compose exec backend python scripts/weekly_budget_accrual.py --dry-run
```

Erwartet: Für jede Nutzerin eine Zeile mit `⟲ Schuljahreswechsel, Verbrauch wird genullt`
und der neuen Grenze in Höhe **eines** Wochenbetrags.

Steht dort stattdessen „keine Unterrichtswoche", liegt der Stichtag noch in den Ferien —
das ist vor dem ersten Schultag richtig so.

---

## Prüfen, dass es gewirkt hat

Nach dem ersten Lauf im neuen Schuljahr:

```bash
docker compose exec backend python scripts/weekly_budget_accrual.py --dry-run
```

Erwartet: `diese Woche bereits gebucht` für alle. Ein zweiter Lauf darf nichts tun — das
ist die Idempotenz, auf der der ganze wöchentliche Betrieb beruht.

Auf `/budget` sollte die Hochrechnung neu bei null beginnen und als **unsicher**
gekennzeichnet sein (unter vier vergangenen Wochen).

## Wenn etwas schiefging

| Beobachtung | Ursache | Abhilfe |
|---|---|---|
| Zu viele Unterrichtswochen | Ferienzeitraum fehlt in `school_year.yaml` | Ergänzen; die Zahl auf `/budget` prüfen. Bereits gebuchte Wochen bleiben — die Grenze wird nie gekürzt |
| Nutzer:innen ohne Budget | `budget_tiers.yaml` führt noch `max_budget_eur` | Auf `wochenbudget_eur` umstellen, Fehler steht im Log |
| Verbrauch nicht zurückgesetzt | Erster Lauf lief noch mit dem alten `school_year.yaml` | `school_year.yaml` korrigieren; der nächste Lauf erkennt den Wechsel dann |
| „keine Unterrichtswoche" bei allen | Stichtag in den Ferien oder außerhalb des Schuljahres | Kein Fehler — vor dem ersten Schultag erwartet |

## Weiter

- [Budget-System](../admin/budget.md) — Modell, Hochrechnung, Umstellung
- [Updates & Wartung](../admin/updates-und-wartung.md) — Abgänger, SSO-Gruppen
- [Stundenplan-Integration](../admin/stundenplan-integration.md) — Ferienimport
