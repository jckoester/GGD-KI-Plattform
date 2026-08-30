# Budget-System

## Konzept

Jede Nutzerin und jeder Nutzer hat ein Budget in Euro **je Unterrichtswoche**. Günstigere
Modelle verbrauchen es langsamer; leistungsstärkere schneller.

**Es wird nichts zurückgesetzt.** Die persönliche Obergrenze wächst jede Unterrichtswoche
um den eingetragenen Betrag, der Verbrauch läuft das Schuljahr durch. Was in ruhigen Wochen
übrig bleibt, steht in dichten Wochen zusätzlich zur Verfügung — Ferien und
Klassenarbeitsphasen gleichen sich dadurch von selbst aus.

Damit daraus kein Ansparkonto wird, eilt die Obergrenze dem Verbrauch höchstens
`vorsprung_wochen` Wochenbeträge voraus (Vorgabe: 3). Wer ein halbes Jahr nichts nutzt,
sammelt kein halbes Jahr an. Das ist die Tempobegrenzung, die früher die monatliche
Rücksetzung übernommen hat.

Welche Wochen Unterrichtswochen sind, steht in `school_year.yaml`; Ferienwochen bekommen
keine Zuteilung. Die **Jahressumme** ist `Wochenbetrag × Unterrichtswochen` — der Betrag,
auf den sich die Schule festlegt. Die Admin-Oberfläche zeigt ihn beim Eintragen an.

Überschreitungen lehnt der Proxy ab; die Plattform zeigt Nutzer:innen dann eine
verständliche Meldung.

### Währung — die Stelle, an der ein Budget still danebenliegt

Budgets sind in Euro gedacht. Durchgesetzt werden sie gegen die Preise in der
LiteLLM-Config, und **beide müssen dieselbe Einheit haben.** Welche das ist, sagt
`LITELLM_PRICE_CURRENCY`:

- **`EUR`** — die Preise sind bereits Euro, es wird **nicht umgerechnet** (Faktor 1,0).
  Der Regelfall bei Anbietern, die in Euro abrechnen; IONOS listet ausschließlich
  Euro-Preise.
- **`USD`** *(Vorgabe)* — die Preise sind Dollar, EUR-Budgets werden mit dem monatlich
  abgerufenen EZB-Kurs umgerechnet.

> ⚠️ **Warum Euro-Preise nicht „mal eben" umgerechnet werden sollten.** Wer sie zum
> Tageskurs in Dollar einträgt, friert diesen Kurs in der Config ein — das Budget rechnet
> aber mit dem *aktuellen*. Beide kürzen sich nur, solange die Kurse gleich sind:
>
> ```
> Anbieter berechnet:  N × P_eur
> LiteLLM zählt:       N × P_eur × K_config     ← eingefroren
> Budget erlaubt:      B_eur × K_jetzt          ← aktuell
> ⇒ erlaubter Verbrauch = B_eur × (K_jetzt / K_config)
> ```
>
> Wertet der Euro auf, überschreitet die Schule ihr Budget genau um diesen Faktor — Monat
> für Monat. Nichts schlägt fehl, Statistiken sehen plausibel aus, die Rechnung ist
> trotzdem zu hoch. Mit `EUR` entfällt die Umrechnung und damit das Risiko vollständig.

**Kein pauschaler Sicherheitsabschlag.** Naheliegend wäre, die Budgets um einige Prozent zu
kürzen. Das ist aber das falsche Werkzeug: Der Abschlag wirkt auf die *Zuteilung*, das
Kursrisiko auf den *tatsächlichen Verbrauch* — er kostet also ein Vielfaches dessen, was er
absichert, wirkt nur in eine Richtung, und macht jede angezeigte Zahl (auch die
Jahressumme) falsch. Wer Sicherheit will, verteilt weniger als den vollen Jahrestopf; das
ist transparent und tut dasselbe.

**Im Mischbetrieb** bleibt für den umgerechneten Anteil ein Restrisiko. Es wird sichtbar
statt überdeckt: `python scripts/check_litellm_config.py` meldet Modelle, deren Preise
nicht zur eingestellten Währung passen können — erkennbar daran, dass sie **keine eigene
`api_base`** haben und ihre Preise deshalb aus LiteLLMs eingebauter Tabelle beziehen, die
durchgängig in **USD** geführt wird (bei Mistral nachgeprüft).

> **Einen Rückfall auf ein anderes Modell gibt es nicht.** Budget aufgebraucht heißt:
> keine Nutzung bis zum nächsten Zeitraum (siehe [Modell-Szenarien](modell-szenarien.md)).
>
> **Hinweis für die Fehlersuche:** Der HTTP-Status dieser Ablehnung ist **nicht**
> festgelegt — LiteLLM 1.83.7 antwortet mit `400`, ältere Fassungen mit `429`. Maßgeblich
> ist `type: budget_exceeded` im Antwortkörper; danach sucht auch das Backend. Wer im
> Proxy-Log nach `429` filtert, findet die Fälle nicht.

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
docker compose exec backend python scripts/monthly_team_reconcile.py
```

## Bildgenerierung

Bildgenerierung hat **kein separates Kontingent** — der Bild-Aufruf läuft über den
Virtual Key der Nutzer:in und zählt gegen **dasselbe** monatliche USD-Budget wie
Chat-Nachrichten. Ein Bild ist dabei in der Regel **teurer** als eine Textnachricht,
verbraucht das Budget also schneller (bewusst so). Ist das Budget erschöpft, lehnt
LiteLLM auch den Bild-Aufruf ab, und der Assistent formuliert eine Absage — mit dem
Hinweis auf den nächsten Abrechnungszeitraum, nicht als technischer Fehler.

Die Bild-Kosten werden mitgebucht: Das Backend liest den `x-litellm-response-cost`-Header
des Bild-Aufrufs und addiert ihn zu `messages.cost_usd` / `total_cost_usd`. Für bekannte
Modelle (z. B. `gpt-image-*`) liefert LiteLLM diesen Header automatisch. Für Custom-/lokale
Bild-Modelle ohne hinterlegtes Pricing in der LiteLLM-Config `input_cost_per_image` setzen —
sonst zählt der Bild-Spend 0.

## Cron-Jobs

Zwei automatische Jobs sorgen dafür, dass Budgets korrekt verwaltet werden:

| Job | Zeitplan | Beschreibung |
|-----|---------|-------------|
| ECB-Wechselkurs abrufen | 1. des Monats, 06:00 Uhr | Holt den aktuellen EUR→USD-Kurs |
| Team-Abgleich | 1. des Monats, 07:00 Uhr | Gleicht die LiteLLM-Team-Zugehörigkeit an (Jahrgang/Rolle) |
| **Budget-Zuteilung** | **montags, 05:00 Uhr** | Hebt die Obergrenzen um einen Wochenbetrag an |

Bei Bedarf manuell ausführen:

```bash
docker compose exec backend python scripts/refresh_ecb_rate.py
docker compose exec backend python scripts/monthly_team_reconcile.py
docker compose exec backend python scripts/weekly_budget_accrual.py --dry-run
```

> Der Zuteilungslauf ist **idempotent**: Zweimal in derselben Unterrichtswoche ausgeführt
> bucht er einmal. Fällt er aus, holt der nächste die fehlenden Wochen nach — begrenzt
> durch denselben Vorsprung, ein ausgefallener Cron ist also kein Freibrief. In
> Ferienwochen tut er nichts.

## Schuljahreswechsel

**Der einzige Reset im ganzen Modell — und er braucht keinen eigenen Lauf.**

Sobald in `config/school_year.yaml` ein neues Schuljahr steht, erkennt der Zuteilungslauf
das am Merkposten (`budget_accrual.schuljahr`) und setzt beim ersten Lauf des neuen Jahres
**Obergrenze und Verbrauch** zurück. Die Nutzerin startet mit genau einem Wochenbetrag.

**Reste wandern nicht ins nächste Schuljahr.** Das ist die Zusage, die auch in der
Admin-Oberfläche steht: Was im Juli übrig ist, ist im September nicht mehr da. Wer es
verwenden will, hebt die Wochenbeträge rechtzeitig an — dafür ist die Hochrechnung da.

Checkliste zum Wechsel (ausführlich im [Runbook](../runbooks/schuljahreswechsel.md)):

1. `config/school_year.yaml` auf das neue Schuljahr umstellen (Beginn, Ende, Ferien,
   Feiertage). Der Ferienimport hilft: `/settings` → Ferien übernehmen.
2. **Die Zahl der Unterrichtswochen prüfen** — sie steht auf `/budget` und ist der Faktor
   der Jahreszusage. Ein vergessener Ferienzeitraum erzeugt zusätzliche Wochen und damit
   eine höhere Jahressumme, als beim Eintragen angezeigt wurde.
3. Wochenbeträge je Stufe prüfen und ggf. anpassen.
4. Den ersten Zuteilungslauf abwarten (montags) oder von Hand anstoßen:
   `docker compose exec backend python scripts/weekly_budget_accrual.py --dry-run`

> Der Lauf setzt **nur** beim erkannten Jahreswechsel zurück. Eine Nutzerin ohne
> Merkposten — etwa direkt nach der Umstellung vom Monatsmodell — behält ihren Verbrauch;
> ihn stillschweigend zu löschen wäre Datenverlust.

## Umstellung vom Monatsmodell (einmalig)

Bis 08/2026 war das Budget monatlich und wurde von LiteLLM zurückgesetzt. Bestandsnutzer
tragen dafür ein `budget_duration: 1mo`. **Solange das steht, setzt LiteLLM ihren Verbrauch
weiterhin monatlich zurück** — der Wochenlauf liefe daneben her, ohne dass etwas
fehlschlägt.

```bash
# 1. budget_tiers.yaml auf `wochenbudget_eur` umstellen (Vorlage: .example)
# 2. Zeitraum entfernen (--verbrauch-zuruecksetzen zum Schuljahresbeginn)
docker compose exec backend python scripts/migrate_budget_duration.py --dry-run
docker compose exec backend python scripts/migrate_budget_duration.py --verbrauch-zuruecksetzen
# 3. Obergrenzen aus den Wochenbeträgen neu aufbauen
docker compose exec backend python scripts/weekly_budget_accrual.py --neuaufbau
```

> **Diese Reihenfolge einhalten.** Bei LiteLLM bedeutet `max_budget = NULL` *und*
> `max_budget = 0` gleichermaßen **kein Limit** (gemessen). Die Migration lässt die
> Obergrenzen deshalb bewusst stehen; erst der Neuaufbau ersetzt sie. So gibt es zu keinem
> Zeitpunkt ein Konto ohne Limit.
>
> `--neuaufbau` ist der **einzige** Modus, der eine Obergrenze senkt. Er setzt sie auf
> „bisheriger Verbrauch + ein Wochenbetrag", sperrt also niemanden aus. Im Regellauf wird
> nie gekürzt.

> ⚠️ **Schritt 3 schreibt nur innerhalb einer Unterrichtswoche.** Fällt der Stichtag in
> die Ferien oder außerhalb des Schuljahres, das `config/school_year.yaml` führt, gibt es
> nichts zuzuteilen — der Lauf endet mit `gebucht=0` und `keine Unterrichtswoche=<n>` und
> **lässt die alten Monatsgrenzen stehen**. Das gilt auch für den wöchentlichen Cron.
>
> Das ist richtig so (in den Ferien wächst kein Budget), aber leicht zu übersehen: Der
> Lauf meldet keinen Fehler, und die Konten sehen weiter versorgt aus — mit einem
> Monatsbetrag, also je nach Stufe einem Vielfachen des vorgesehenen Wochenbetrags.
>
> Deshalb: Nach Schritt 3 den Kopf des Logs lesen. Dort steht das Schuljahr, das die
> Konfiguration führt, und der Stichtag:
>
> ```
> Schuljahr 2026/27 · Stichtag 2026-09-14 · Kurs 1.0000 · Vorsprung 3 Wochen · 7 Nutzer
> ```
>
> Passen die beiden nicht zusammen, ist zuerst `school_year.yaml` an der Reihe
> ([Schuljahreswechsel](../runbooks/schuljahreswechsel.md)) — sonst findet **nie** eine
> Zuteilung statt, und der Jahreswechsel-Reset löst ebenfalls nicht aus: Er hängt daran,
> dass die Konfiguration ein neues Schuljahr führt.
>
> Die Umstellung lässt sich in den Ferien vorbereiten; die Grenzen setzt dann der erste
> Montagslauf der ersten Unterrichtswoche. `--neuaufbau` ist dafür nicht nötig — und im
> Zweifel besser nicht zu wiederholen, weil er sich am jeweils aktuellen Verbrauch neu
> verankert.

## Hochrechnung aufs Schuljahr

Über der Stufentabelle steht, wohin das Schuljahr läuft:

> Bisher verbraucht: **143,20 €** in 12 von 40 Unterrichtswochen. Bei diesem Tempo endet
> das Schuljahr bei **477,33 €** von 2.053,00 € zugeteilt (23 %).

**Der Sinn ist der Zeitpunkt.** Im Juli weiß jeder, ob die Schule unter ihrer Zusage
geblieben ist — dann ist der Rest nur noch zu verwalten. Im März lassen sich die
Wochenbeträge fürs zweite Halbjahr noch anheben, und *das* ist die sinnvolle Verwendung
nicht abgeflossener Mittel. Bei einer erwarteten Auslastung unter 60 % weist die Seite
ausdrücklich darauf hin; bei über 100 % ebenso, dann in die andere Richtung.

Der Verbrauch stammt aus der **eigenen** Datenbank (`messages.cost_usd`, Bildkosten
eingeschlossen), nicht aus dem Proxy — dort wäre er nur je Nutzer abrufbar, und
achthundert Einzelabfragen für eine Übersichtsseite verbieten sich.

> **Was die Zahl nicht kann.** Sie schreibt den bisherigen Verbrauch **linear** fort und
> kennt keine Saison: Klassenarbeitsphasen und Projekttage schlagen erst durch, wenn sie
> stattgefunden haben. In den ersten Wochen ist sie deshalb Rauschen — eine einzelne
> Projektwoche verdoppelt sie. Bis vier vergangene Wochen erreicht sind, kennzeichnet die
> Seite sie als unsicher, zeigt sie aber trotzdem: Sie zu verschweigen hieße, die
> Administration bis Weihnachten im Dunkeln zu lassen.
>
> Etwas Klügeres als eine lineare Fortschreibung wäre Scheingenauigkeit — es gibt keine
> Vorjahresdaten, an denen sich ein Saisonmuster ablesen ließe.

## Admin-Übersicht (`/budget`)

Im Admin-Bereich zeigt `/budget` eine aggregierte Übersicht der Ausgaben —
aufgeschlüsselt nach Nutzergruppen und Jahrgängen. Die Anzeige ist
pseudonymisiert: es sind keine Klarnamen sichtbar.

Für rechtlich begründete Einzelfälle (z. B. Missbrauchsverdacht) ist eine
De-Anonymisierung über das Audit-Log möglich — dies wird protokolliert.
Details dazu in [Datenschutz & Betrieb](datenschutz-betrieb.md).
