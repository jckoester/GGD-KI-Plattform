# Stundenplan-Integration (WebUntis)

Die Plattform kann den Stundenplan aus **WebUntis** lesen und daraus dreierlei ableiten:
den **Ferienkalender**, die **Wochenmuster** der Unterrichtsgruppen und den täglichen
**Abgleich von Entfall, Vertretung und Verlegung** mit der Jahresplanung.

> **Die Integration ist durchgehend ein Beschleuniger, kein Muss.**
> Ohne sie funktioniert die Unterrichtsplanung vollständig: Ferien und Feiertage stehen
> dann von Hand in `config/school_year.yaml`, Wochenmuster werden im Jahresplan eingetippt,
> Ausfall wird beim Nachbereiten gesetzt. Kein Pflichtfeld hängt an WebUntis — ist keine
> Quelle eingerichtet, verschwinden lediglich die zugehörigen Bedienelemente.

---

## Voraussetzung: ein technisches Servicekonto

Der Abruf läuft über **ein** schulweites Dienstkonto, nicht über die persönlichen Zugänge
der Lehrkräfte. Das Konto braucht Leserechte auf die Lehrerpläne.

**Was das Konto sehen können muss:**

| Fähigkeit | Wofür |
|---|---|
| Lehrkräfte mit Kürzel aufzählen | Auswahlliste im Profil |
| Wochenplan einer Lehrkraft lesen | Muster und Abgleich |
| Ferien lesen (`getHolidays`) | Ferienkalender |
| Zeitraster lesen (`getTimegridUnits`) | Doppelstunden erkennen |

**Was es nicht können muss** — und aus Datenschutzsicht besser auch nicht kann: Klassen
und Schüler:innen aufzählen. Ein Konto ohne diese Rechte reicht vollständig aus.
Lassen Sie es sich so einrichten (siehe [Datenschutz](#datenschutz)).

Vor der Einrichtung lässt sich ein Konto mit dem Diagnoseskript prüfen:

```bash
export WEBUNTIS_BASE="ihre-schule.webuntis.com"   # mit oder ohne https://
export WEBUNTIS_USER="<servicekonto>"
export WEBUNTIS_SCHOOL=""                         # nur bei geteiltem Server
read -rs WEBUNTIS_PASSWORD && export WEBUNTIS_PASSWORD

python scripts/webuntis_probe.py
```

> Das Diagnoseskript nutzt **`WEBUNTIS_BASE`**, die Anwendung **`WEBUNTIS_SERVER`** — der
> Wert ist derselbe, die Variablennamen sind es nicht.

Das Skript meldet, was das Konto sieht, wie weit es zurückblicken kann und welche Felder
die Wochenschnittstelle liefert. Zugangsdaten werden **nur** aus der Umgebung gelesen, nie
in die Datei geschrieben; ohne gesetztes Passwort fragt es interaktiv nach.

---

## Konfiguration

Die Zugangsdaten stehen in der **`.env`** — es ist ein einziges Geheimnis, also dieselbe
Behandlung wie `SCHOOL_SECRET` oder `LITELLM_MASTER_KEY`. Es gibt bewusst **keine
Verwaltungsoberfläche** dafür.

```bash
# ── Stundenplan (WebUntis) ─────────────────────────────────────────────
WEBUNTIS_SERVER=ggd.webuntis.com   # mit oder ohne https://
WEBUNTIS_USER=
WEBUNTIS_PASSWORD=
WEBUNTIS_SCHOOL=                   # meist leer lassen — siehe unten
```

> **`WEBUNTIS_SCHOOL` nur bei geteiltem Server setzen.** Hat die Schule eine eigene
> Subdomain (`ihre-schule.webuntis.com`), muss das Feld **leer** bleiben — sonst
> antwortet WebUntis mit `invalid schoolname` (Fehler `-8500`).

**`WEBUNTIS_SERVER` leer = Integration aus.** Dann verschwinden Kürzel-Feld, Ferien-Seite
und Abgleich-Knopf aus der Oberfläche. Der Servername allein entscheidet darüber;
Benutzername und Passwort werden erst beim Verbinden geprüft, damit eine halb ausgefüllte
Konfiguration einen Fehler meldet, statt sich als „nicht vorhanden" zu tarnen.

### Fachkürzel zuordnen

Die Kürzel des Stundenplans (`M`, `ETH`, `SPW`) sind ein **eigenes Vokabular** — weder der
Fach-Slug noch die SSO-Aliase noch der Bildungsplan-Code. `ETH` ist nicht `ET`, `INFWFO`
nicht `INF`. Deshalb trägt jedes Fach in `config/subjects.yaml` seine Stundenplan-Kürzel
selbst:

```yaml
untis_kein_unterricht: [PRÄS, ÖPR, SL]   # keine Fächer, werden nie welche

subjects:
  - slug: mathematik
    untis_codes: [M]
  - slug: sport
    untis_codes: [SP, SPM, SPW]          # mehrere Kürzel, ein Fach
```

Danach: `python scripts/seed_subjects.py`.

**Zwei Regeln, die beim Pflegen wichtig sind:**

1. **Groß- und Kleinschreibung trägt Bedeutung.** Kleingeschrieben = Basiskurs der
   Kursstufe, großgeschrieben = Leistungskurs **oder** regulärer Unterricht in Sek I. Die
   Fachauflösung ist unempfindlich dagegen, die Gruppenzuordnung nicht — Basis- und
   Leistungskurs desselben Fachs sind zwei verschiedene Gruppen.
2. **Ziffern sind Parallelkurse** (`M1`, `bio2`). Sie werden automatisch abgeschnitten,
   wenn das volle Kürzel nicht trifft — aber erst dann, denn `L2` ist ein eigenes Fach.

`untis_kein_unterricht` listet Kürzel, die im Plan stehen, aber kein Unterricht sind
(Präsenzstunden, Personalrat, Schulleitungssitzungen). Sie werden übergangen, **ohne** als
„unbekanntes Fach" gemeldet zu werden. Die Liste ist Konfiguration, kein Code — jede Schule
nutzt andere Kürzel.

Kürzel, die weder zugeordnet noch ausgenommen sind, meldet der Abgleich mit ihrer
Häufigkeit. Das ist die Arbeitsliste zum Nachpflegen.

---

## Ferienkalender übernehmen

**`/settings/holidays`** (nur sichtbar, wenn WebUntis eingerichtet ist) holt die Ferien und
beweglichen Ferientage aus WebUntis und schreibt sie nach `config/school_year.yaml`.

Warum nicht einfach ein Landeskalender aus dem Netz: Die acht **beweglichen Ferientage**
legt jede Stadt beziehungsweise Schule selbst, und sie stehen in **keinem** allgemeinen
Kalender. Ein generischer BW-Feed läge also garantiert an genau den Tagen falsch, an denen
es darauf ankommt.

**Ablauf:** Schuljahr wählen → Vorschlag ansehen → übernehmen. Die Seite zeigt vorab, was
sich ändert.

Drei Eigenschaften, die man kennen sollte:

- **Der Vorschlag ergänzt, er ersetzt nicht.** Beide Seiten kennen Tage, die die andere
  nicht hat: WebUntis kennt Faschingsferien und bewegliche Ferientage, die Handpflege kennt
  Reisewoche und letzten Schultag. Ein Ersetzen verlöre die zweite Hälfte.
- **Die alte Datei wird als `.bak` gesichert**, bevor die neue geschrieben wird.
- **Der Halbjahreswechsel bleibt Handarbeit.** Die Schnittstelle kennt ihn nicht.

Einmal je Schuljahr ausführen. Die Daten sind stabil — bewegliche Ferientage stehen Jahre
im Voraus fest. Was sich unterjährig ändert (Wandertage, pädagogische Tage), kommt nicht
von hier, sondern über den täglichen Abgleich als ganztägiger Ausfall.

---

## Täglicher Abgleich

Der Cron läuft **werktags um 5:30 Uhr** und gleicht für jede Lehrkraft mit hinterlegtem
Kürzel die letzten vier Unterrichtswochen einschließlich der laufenden plus zwei Wochen
voraus ab. Der Blick nach vorn ist kein Luxus: Das **Ziel** einer Verlegung liegt fast
immer in einer kommenden Woche — ein reiner Rückblick fände den Ausfall und nie den
Ersatztermin.

```
30 5 * * 1-5 root python /app/scripts/sync_timetable.py
```

Manuell, etwa zur Kontrolle:

```bash
docker compose exec backend python scripts/sync_timetable.py --dry-run
docker compose exec backend python scripts/sync_timetable.py --wochen 2 --bis 2026-07-10
```

> **Der Cron ist das Sicherheitsnetz, nicht der Hauptweg.** An vielen Schulen werden
> Vertretungen erst wenige Minuten vor Unterrichtsbeginn eingetragen — ein nächtlicher Lauf
> sieht sie erst am Folgetag. Für den Tagesbedarf gibt es den **Handabgleich**: Lehrkräfte
> lösen ihn im Jahresplan oder im Profil selbst aus (siehe
> [Anwender-Doku](../user/stundenplan.md)). Bei Ausfall ist ein Tag Verzug verkraftbar, bei
> Verlegungen nicht.
>
> Mehrere Cron-Läufe über den Tag wurden bewusst verworfen: Sie änderten die Planung,
> während Lehrkräfte daran arbeiten.

### Fail-open — zweifach

| Ebene | Verhalten |
|---|---|
| **Je Lehrkraft** | Ein Kürzel, das WebUntis nicht kennt, stoppt die übrigen 89 nicht. Jede wird einzeln abgeglichen und einzeln vermerkt. |
| **Je Lauf** | Ist die Quelle nicht erreichbar, bleibt die Planung **unverändert**. Es wird nichts verworfen, nichts zurückgesetzt. |

Das ist die wichtigste Zusage des Abgleichs: Die Jahresplanung ist Handarbeit. Sie zu
beschädigen, weil ein fremder Server kurz nicht antwortet, wäre der teuerste denkbare
Fehler.

Der Lauf endet deshalb auch bei einzelnen Fehlschlägen mit Exit-Code 0 — sonst alarmierte
die Cron-Überwachung täglich, obwohl nichts zu tun ist. Die Fehlschläge stehen im Status.

### Was der Abgleich ändert — und was nicht

**Er ändert** die Kategorie vorhandener Slots (`unterricht` → `ausfall` / `vertretung` /
`pruefung`) und setzt bei Ausfall und Vertretung das Kennzeichen „Anpassung nötig".

**Er ändert nie:**

- Slots mit `pinned` oder von Hand gesetzte Slots — gemeldet als Konflikt, nicht geändert
- Eigene Notizen. Der Abgleich schreibt nur in leere Notizfelder oder in solche, die er
  selbst mit `[Stundenplan]` markiert hat. Der Marker macht ihn zugleich wiederholbar.
- Er **legt keine Slots an**. Kennt der Stundenplan Unterricht, den die Jahresplanung nicht
  hat, ist das eine Abweichung zum Ansehen, keine Aufgabe zum Ausführen.

**Verlegungen** erscheinen als Vorschlag, nicht als Änderung. Eine Verlegung ist in WebUntis
ein Paar (Ursprung entfällt, Ziel entsteht); die Plattform bündelt es zu einem Vorschlag und
öffnet damit den vorhandenen Verschiebe-Dialog.

---

## Fehlerbilder

Der letzte Lauf steht je Lehrkraft in `calendar_sync_status` und wird im Profil und am
Jahresplan angezeigt.

| Status | Bedeutung | Was zu tun ist |
|---|---|---|
| `ok` | Abgleich erfolgreich | — |
| `kein_kuerzel` | Im Profil ist kein Kürzel eingetragen | Kein Fehler. Die Lehrkraft nutzt die Integration nicht. |
| `nicht_erreichbar` | Server antwortet nicht oder mit HTTP-Fehler | Netz und Erreichbarkeit prüfen. Daten sind unverändert. |
| `anmeldung_fehlgeschlagen` | Zugangsdaten abgelehnt | `WEBUNTIS_USER`/`WEBUNTIS_PASSWORD` prüfen; ist das Konto gesperrt oder abgelaufen? |
| `fehler` | Sonstiges | Log ansehen. |

> **Fehlermeldungen der Quelle werden nie durchgereicht.** Sie können Zugangsdaten
> enthalten. Unerwartete Ausnahmen werden auf den Typnamen reduziert.

### Häufige Ursachen

**`invalid schoolname` (-8500)** — `WEBUNTIS_SCHOOL` ist gesetzt, obwohl die Schule eine
eigene Subdomain hat. Feld leeren.

**`sy is null` (-8998)** — Die Sitzung hat noch keinen Schuljahresbezug. Das ist der
Normalzustand einer frischen Anmeldung, kein Fehler und **nicht** „kein Schuljahr aktiv".
Die Plattform prägt ihn selbst auf; tritt der Fehler dauerhaft auf, fehlt dem Konto
vermutlich das Klassenbuchrecht (dann greift ein Rückfallweg) oder die Anmeldung schlägt
schon vorher fehl.

**Kürzel-Feld erscheint nicht im Profil** — `WEBUNTIS_SERVER` ist leer oder das Backend
wurde nach der `.env`-Änderung nicht neu gestartet.

**Eine Lehrkraft findet ihre Gruppe im Vorschlag nicht** — meist heißt die Gruppe im
Stundenplan anders als in der Plattform, oder das Fachkürzel fehlt in `untis_codes`. Der
Abgleich meldet unbekannte Kürzel mit Häufigkeit.

**Gruppe wird als `mehrdeutig` gemeldet** — es gibt Basis- und Leistungskurs desselben
Fachs, aber die vorhandene Gruppe trägt die Kursart nicht im Namen. Die Plattform rät hier
bewusst nicht; Gruppe umbenennen.

---

## Datenschutz

Der Abruf erweitert den **Empfängerkreis nicht**: Lehrerpläne sind kollegiumsöffentlich,
Ausfälle und Vertretungen schulintern bekannt. Die Plattform liest sie lediglich maschinell.

- Das Servicekonto sieht **die Pläne aller Lehrkräfte**. Das ist der Punkt, den ein
  Verarbeitungsverzeichnis festhalten muss.
- Es sieht **keine** Schüler:innen — sofern es entsprechend eingerichtet ist. Prüfen Sie das
  mit `webuntis_probe.py`, bevor Sie es freischalten.
- Je Lehrkraft speichert die Plattform **nur das Kürzel** (in `user_preferences`) und den
  **Abrufstatus** (in `calendar_sync_status`). Beides wird mit dem Konto gelöscht.
- Das Kürzel wird **nie an ein Sprachmodell** übergeben.

Details und der Eintrag fürs Verarbeitungsverzeichnis:
[Datenschutz & Betrieb](datenschutz-betrieb.md#stundenplan-integration-webuntis).
