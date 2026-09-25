# Nutzerverwaltung & Rollen

## Rollen im Überblick

| Rolle | Wer | Kann |
|-------|-----|------|
| `student` | Schüler:innen | Chatten, Dateien hochladen, Assistenten nutzen |
| `teacher` | Lehrkräfte | Alles wie student + eigene Assistenten anlegen |
| `admin` | IT-Admin, Schulleitung | Alles + Admin-Bereich (Modelle, Budgets, Statistiken, Texte) |

## Authentifizierung via SSO

Die Plattform verwendet OAuth2/OIDC zur Anmeldung. Nutzer:innen werden nicht
manuell angelegt — Konten entstehen automatisch beim ersten Login.

**Was beim Login passiert:**

1. Die Nutzerin klickt „Anmelden" und wird zum SSO-Provider weitergeleitet.
2. Nach erfolgreicher Anmeldung sendet der SSO-Provider Nutzerinformationen
   zurück: eine eindeutige ID (`external_id`) sowie die Gruppenmitgliedschaften.
3. Das Backend leitet die Gruppe über `group_role_map` zu einer Plattform-Rolle.
4. Aus der `external_id` wird ein anonymes Pseudonym berechnet (HMAC-SHA256).
   **Name und E-Mail-Adresse verlassen den Schulserver nicht.**
5. Ein JWT-Session-Token wird ausgestellt (gültig 30 Tage).

**OAuth2-App beim SSO-Provider anlegen:**

- Client-ID: frei wählbar, z. B. `ki-plattform`
- Redirect-URI: `https://ki.beispielschule.de/auth/callback`
- Benötigte Scopes: `openid`, `profile`, `groups` (o. ä. — Provider-abhängig)
- **Freigabe für die Gruppen**, die die Plattform nutzen dürfen

### Wer die Plattform nutzen darf

**Der Nutzerkreis wird beim SSO-Provider bestimmt, nicht in der Plattform.** Maßgeblich ist,
für welche Gruppen der OAuth-Client freigegeben ist; wer nicht dazugehört, kommt gar nicht
erst bei der Plattform an. Bei lokalen Konten (Testbetrieb) existieren ohnehin nur Konten
für Berechtigte.

> Der Fallback auf die Rolle `student` in `group_role_map` ist **keine** Zugangsregel — er
> bestimmt nur die Rolle für jemanden, der die Anmeldung bereits bestanden hat.

> ⚠️ **„Anmeldung fehlgeschlagen!" trotz richtigem Passwort.** Ist der Client für die
> Gruppe der Person **nicht** freigegeben, bleibt IServ auf der eigenen Login-Seite und
> zeigt genau diese Meldung — obwohl die Anmeldung *in IServ* erfolgreich war. Gemeint ist
> „Die Anmeldung am gewünschten Dienst ist nicht möglich"; der Text kommt von IServ und
> lässt sich von hier aus nicht ändern.
>
> **Für die Fehlersuche heißt das:** Melden Nutzer:innen „Login geht nicht", obwohl die
> Zugangsdaten stimmen, ist die **Client-Freigabe** zu prüfen — nicht das Konto, nicht die
> Plattform. In den Logs der Plattform steht dazu nichts, weil die Anfrage sie nie
> erreicht.
- Client-Secret in `AUTH_ISERV_CLIENT_SECRET` in `.env` eintragen

## Gruppen → Rollen (`group_role_map`)

In `config/auth.yaml` wird festgelegt, welche SSO-Gruppe welche Plattform-Rolle erhält:

```yaml
group_role_map:
  - group: ki-admins
    role: admin
  - group: lehrer
    role: teacher
  - group: schueler
    role: student
```

- Mehrere Gruppen können auf dieselbe Rolle zeigen.
- Nutzer:innen, die keiner zugeordneten Gruppe angehören, können sich
  **nicht** einloggen — sie erhalten eine Fehlermeldung.
- Die Gruppen-Namen müssen exakt mit den Gruppen-Namen im SSO-Provider übereinstimmen.

## Rollenänderungen & Sitzungen beenden

Die Rollen einer Nutzerin stehen im Session-Token (JWT, 30 Tage gültig). Ändert
sich die SSO-Zugehörigkeit, greift das **erst beim nächsten Login** — bis dahin
gilt die im Token gespeicherte Rolle. Das ist vor allem beim **Entzug** additiver
Rollen relevant (z. B. `admin` oder `review` wird einer Lehrkraft weggenommen):
Die laufende Sitzung würde die erhöhten Rechte sonst bis zu 30 Tage behalten.

Zwei Mechanismen adressieren das:

1. **Automatisch beim nächsten Login (Rollen-Schrumpfung):** Meldet sich die
   Nutzerin erneut an und wurde ihr seit dem letzten Login mindestens eine Rolle
   **entzogen**, werden alle zuvor ausgestellten Token sofort ungültig — auch
   parallele Sitzungen auf anderen Geräten. Das neue Token trägt die korrekten,
   reduzierten Rollen. (Reine Hochstufungen lösen das nicht aus, da eine alte
   Sitzung dann nur *weniger* Rechte hätte — kein Sicherheitsproblem.)

2. **Manuell sofort — „Nutzer & Sitzungen":** Unter **Einstellungen → Nutzer &
   Sitzungen** (`/settings/users`) sehen Admins alle Konten mit ihren aktuellen
   Rollen und dem letzten Login. Über **„Sitzungen beenden"** werden alle aktiven
   Sitzungen eines Kontos sofort ungültig; die Person muss sich neu anmelden,
   wobei die Rollen frisch aus dem SSO bewertet werden. Nutze das, wenn der
   Rollenentzug **nicht** bis zum nächsten (freiwilligen) Login der Person warten
   soll. Filter nach Rolle (z. B. `admin`) und Suche nach Pseudonym helfen beim
   Finden des richtigen Kontos.

> **Hinweis:** Der volle Rollensatz wird erst ab dem ersten Login **nach dem
> Update** gespeichert. Für Konten, die sich seither noch nicht angemeldet haben,
> zeigt die Liste ersatzweise nur die Primärrolle (teacher/student), und die
> automatische Schrumpfungs-Erkennung (1.) greift erst ab deren zweitem Login.
> Der manuelle Hebel (2.) funktioniert unabhängig davon jederzeit.

## SSO-Gruppenimport: Unterrichtsgruppen

Wenn der SSO-Provider Gruppen für Fachschaften, Schulklassen und
Unterrichtsgruppen liefert, wertet die Plattform diese beim Login aus. Dafür müssen die
Gruppennamen in `auth.yaml` unter `sso.groups` als Regex-Muster konfiguriert sein.

⚠️ **Angelegt werden sie nicht alle gleich.** Fachschaften, Schulklassen, Lehrkräfte- und
Arbeitsgruppen entstehen automatisch. **Unterrichtsgruppen nicht** — sie werden der
Lehrkraft als *Angebot* vorgelegt (siehe unten). Bis zum 23.09.2026 entstanden auch sie
automatisch; das führte zu Doppelgruppen und in einem Fall zu einem fehlgeschlagenen
Login.

**Matching-Reihenfolge:** Für jede SSO-Gruppe wird der aus dem Gruppenname
extrahierte Wert zunächst direkt (case-insensitiv) mit dem Fach-Slug verglichen.
Schlägt das fehl, wird die `subject_aliases`-Map konsultiert. Gruppen, die
keinem Fach zugeordnet werden können, werden als `WARNING` ins Backend-Log
geschrieben — das ist der Hinweis, dass ein Alias fehlt:

```
WARNING: SSO-Gruppe 'FS.M' (Typ 'subject_department'): Fach-Slug 'M' nicht aufgelöst.
subject_aliases in auth.yaml prüfen.
```

Um das zu beheben, den fehlenden Alias in `auth.yaml` eintragen:

```yaml
sso:
  subject_aliases:
    M: mathematik
```



## Unterrichtsgruppen aus dem Schulkonto: das Angebot

Liefert der SSO eine Unterrichtsgruppe, zu der es auf der Plattform noch keine Gruppe
gibt, **entsteht nichts**. Die Gruppe wird der Lehrkraft unter *Profil → Meine
Unterrichtsgruppen* als **Angebot** vorgelegt; sie entscheidet:

| Antwort | Was passiert |
|---|---|
| **Zuordnen** | Die SSO-Gruppe wird mit einer vorhandenen Unterrichtsgruppe verknüpft. Ab dann führt das Schulkonto die Mitglieder |
| **Als neue Gruppe anlegen** | Eine neue Unterrichtsgruppe entsteht, bereits verknüpft |
| **Ignorieren** | Nichts geschieht. Die Frage kehrt nicht zurück, lässt sich aber wieder einblenden |

### Warum nicht automatisch

Aus den SSO-Daten lässt sich **nicht bestimmen**, ob `unterricht.9d.ch` die vorhandene
Gruppe *Chemie 9D* meint oder eine neue ist: Der Provider liefert einen Namen als
Freitext, keine Klassenzuordnung. `„NwT 9a"` und `unterricht.9a.nwt` sehen nur
*meistens* gleich aus.

Bis zum 23.09.2026 versuchte die Plattform, das über `(Lehrkraft, Fach)` zu erraten. Das
war aus zwei Gründen falsch:

- **Zwei Gruppen im selben Fach sind der Normalfall.** *Chemie 9c* und *Chemie 9d* sind
  getrennter Unterricht mit eigenen Terminen, Ausfällen und Reflexionen — und je einem
  eigenen Stundenplan-Eintrag. Die Heuristik traf beide und brach mit einem Fehler ab;
  die Lehrkraft kam nicht mehr hinein.
- **Eine falsche Verschmelzung ist nicht rückgängig zu machen.** Sie schiebt zwei
  Jahrespläne ineinander.

Eine Dublette ist unbequem, ein falscher Zusammenschluss ist teuer. Deshalb wird gefragt.

### Was beim Scharfschalten zu erwarten ist

Wird im Schulkonto die Unterrichtsgruppen-Synchronisation neu aktiviert, sehen die
Lehrkräfte beim nächsten Login **ein Angebot je Gruppe**. Nichts ändert sich, bis sie
antworten. Bestehende Gruppen, Jahrespläne und Chats bleiben unberührt.

**Die erste Antwort gilt für alle.** Bei kooperativ unterrichteten Kursen sehen mehrere
Lehrkräfte dasselbe Angebot; sobald eine es beantwortet hat, verschwindet es bei den
übrigen. Ohne diese Regel legte die zweite Antwort eine Doppelgruppe an.

### Folgen einer Zuordnung

- Die Mitglieder kommen ab dem nächsten Login aus dem Schulkonto (Herkunft `sso`).
- **Über die Klasse geerbte Mitgliedschaften werden entfernt.** Die Vererbung ist für
  SSO-Gruppen abgeschaltet; bliebe das Geerbte stehen, räumte es niemand mehr auf — auch
  der Immediate Mirror nicht, der nur `sso` anfasst.
- **Beitritte per Code bleiben.** Sie sind die Entscheidung eines Menschen. Der
  Beitrittscode wird für die Gruppe allerdings ausgeblendet: Wo das Schulkonto die
  Mitglieder führt, gäbe ein zweiter Weg hinein zwei Wahrheiten.
- Jahresplan, Stundenentwürfe und Konversationen bleiben unberührt.

## Woher Mitgliedschaften kommen — und wer sie aufräumt

Auf Ebene 2 (Unterrichtsgruppen) gibt es **fünf** Wege, auf denen ein Pseudonym Mitglied
wird. Sie stehen explizit in `group_memberships.herkunft`, weil sich daraus ergibt, was
ein Aufräumlauf anfassen darf:

| Herkunft | Wie sie entsteht | Wer entfernt sie automatisch |
|---|---|---|
| `sso` | Der Provider nennt die Person in der Gruppe | **Immediate Mirror** beim Login — er entfernt, was das Token nicht mehr deckt |
| `geerbt` | Schüler:in der Quellklasse einer Unterrichtsgruppe | **Vererbungslauf** beim Login — er entfernt, wo die Quellklasse nicht mehr passt |
| `code` | Selbstbeitritt per Beitrittscode | niemand — nur die Lehrkraft, durch Rücknahme einer Code-Runde |
| `eigen` | Die Lehrkraft, die die Gruppe angelegt hat | niemand |
| `manuell` | Admin über `POST /groups/{id}/members` | niemand |

**Die Regel dahinter:** Ein Aufräumlauf darf nur entfernen, was er selbst hätte anlegen
können. Alles andere ist die Entscheidung eines Menschen und fällt nicht von allein.

⚠️ **Bis Alembic `0068` war die Herkunft geraten** — der Vererbungslauf löschte beim
Abgang alles mit `role_in_group = 'student'`. Das war richtig, solange jede
Schüler-Mitgliedschaft geerbt war; mit dem Beitrittscode stimmt es nicht mehr. Wer die
Bedingung dort wieder auf die Rolle umstellt, wirft jeden Nachzügler aus jeder Gruppe,
die zufällig auch eine Quellklasse hat.

### Erbt eine Gruppe oder nicht?

`groups.erbt_mitglieder` (Alembic `0069`) entscheidet, ob die Schüler:innen der
Quellklassen automatisch Mitglied werden. Die Lehrkraft beantwortet die Frage beim
Anlegen; vorgeschlagen wird sie nach der Lage — bei **genau einer** Klasse „ganze
Klasse", bei mehreren und in der Kursstufe „Teilgruppe".

Das ist bewusst **entschieden und nicht gezählt**: Auch eine einzelne Klasse kann geteilt
sein (Religion und Ethik nennen nur einen Klassennamen), und zwei kleine Klassen können
vollständig gemeinsam unterrichtet werden. Beides weiß nur die Lehrkraft.

Wird der Wert später auf `false` gesetzt, räumt der Vererbungslauf die bisher geerbten
Mitgliedschaften beim nächsten Login ab — die Entscheidung ist also korrigierbar.

### Beitrittscodes

`group_join_codes` hält je Gruppe den aktuellen Code. Gültigkeit **drei Tage**,
erneuerbar; es gilt immer nur einer je Gruppe. Der Code gehört der **Gruppe**, nicht
einer Person: Er trägt kein Personenmerkmal und wird deshalb nicht personenbezogen
gelöscht. Nur `erstellt_von_pseudonym` fällt unter die 90-Tage-Frist und wird dann
genullt — der Code selbst bleibt gültig, bis er abläuft.

Das Einlösen ist gedrosselt (`group_join` in `rate_limits.yaml`, Vorgabe 10 Anfragen je
5 Minuten und Person). **Das Lesen des Codes ist es nicht** — sonst sperrte sich eine
Lehrkraft aus ihrer eigenen Gruppenansicht aus.

## Verwaiste Unterrichtsgruppen finden

Eine Unterrichtsgruppe **ohne Lehrkraft** ist für niemanden mehr erreichbar: Die
Jahresübersicht verlangt eine Lehrkraft-Mitgliedschaft, und die Gruppenliste einer
Lehrkraft zeigt nur eigene Gruppen. Jahresplan, Stundenentwürfe und Konversationen
bleiben trotzdem stehen.

**Das entsteht im laufenden Betrieb**, nicht nur beim Ausprobieren — zwei Wege:

- Der **Immediate Mirror** entfernt die Mitgliedschaft, sobald die Schulkonto-Gruppe
  nicht mehr im Token steht.
- Der **90-Tage-Löschlauf** nimmt sie mitsamt dem Konto. Bei einer Lehrkraft, die die
  Schule verlässt, ist das der Normalfall.

```bash
curl -s -b "session=$TOKEN" \
  "https://.../api/admin/groups?ohne_lehrkraft=true" | jq '.total, .items[].name'
```

Der Filter gilt nur für Unterrichtsgruppen: Eine Klasse ohne Lehrkraft ist der
Normalfall, eine Fachschaft hat ohnehin nur welche. Ein Treffer ist deshalb immer ein
Befund. Übernehmen kann die Gruppe dann eine Lehrkraft, die Sie als Mitglied eintragen
(siehe unten) — oder Sie lassen sie stehen, bis klar ist, ob noch jemand den Jahresplan
braucht.

## Die Gruppen-API für Reparaturen

Unter `/admin/groups` liegen acht Endpunkte (auflisten, anlegen, ansehen, ändern,
löschen, Mitglieder lesen, Mitglied eintragen, Mitglied entfernen). Sie haben **bewusst
keine Oberfläche**: Mitgliederpflege von Hand ist im Regelbetrieb ausgeschlossen, weil
die Plattform keine Klarnamen zeigt — eine Liste aus Pseudonymen wäre nicht bedienbar
(ADR-003, Ebene 2).

Für die **Reparatur** ist das etwas anderes. Dort liegt genau ein Pseudonym vor, und es
kommt aus dem Audit-Log: Sie wissen, wen Sie eintragen wollen, und Sie tragen genau den
ein.

```bash
# Lehrkraft einer verwaisten Gruppe zuordnen
curl -s -X POST -b "session=$TOKEN" -H 'Content-Type: application/json' \
  -d '{"pseudonym": "<aus dem Audit-Log>", "role_in_group": "teacher"}' \
  "https://.../api/admin/groups/<id>/members"
```

Die so entstandene Mitgliedschaft trägt `herkunft = 'manuell'` und wird von **keinem**
Aufräumlauf entfernt — auch nicht von der Rücknahme einer Beitrittscode-Runde. Das ist
Absicht: Was ein Mensch entschieden hat, fällt nicht von allein.

## Unterrichtsgruppen manuell anlegen

Lehrkräfte können Unterrichtsgruppen auch manuell anlegen, wenn der SSO-Provider
sie nicht automatisch liefert. Das Verhalten wird über das Flag
`allow_manual_teaching_groups` in `auth.yaml` gesteuert:

| Wert | Verhalten |
|------|-----------|
| `true` (Standard) | Lehrkräfte sehen Vorschläge in der Sidebar und können bestätigen oder ablehnen |
| `false` | Vorschläge werden nicht angezeigt; `POST /api/groups/teaching` **und** `POST /api/calendar/teaching-groups` geben HTTP 403 zurück |

Der Schalter gilt für **beide** Wege, auf denen eine Lehrkraft eine Unterrichtsgruppe
anlegen kann: „Klasse × Fach" und das Anlegen aus dem eigenen Stundenplan. Der zweite ist
besser belegt, erzeugt aber dieselbe Art Gruppe — und in einer Installation, die auf den
SSO setzt, dieselben Dubletten.

`false` empfiehlt sich, wenn der SSO-Provider alle Unterrichtsgruppen
zuverlässig liefert — so werden manuelle Inkonsistenzen vermieden.
Bereits angelegte manuelle Gruppen und abgelehnte Kombinationen bleiben auch
bei `false` sichtbar und können aufgeräumt werden.

Änderungen an `auth.yaml` werden erst nach einem Backend-Neustart wirksam.



Der Jahrgang einer Schülerin oder eines Schülers steuert das Budget-Tier
(siehe [Budget-System](budget.md)). Er wird automatisch aus der SSO-Gruppe
extrahiert, wenn `grade_group_pattern` in `auth.yaml` gesetzt ist.

```yaml
# Extrahiert "10" aus einer Gruppe namens "jahrgang.10"
grade_group_pattern: '^jahrgang\.(\d{1,2})$'
```

Der Regex muss eine Capture-Group enthalten, deren Inhalt als Jahrgang (Zahl)
interpretiert wird. Wenn keine Jahrgangsgruppe erkannt wird, erhält die
Nutzerin kein jahrgangsbasiertes Budget — sie fällt auf das Rollen-Budget zurück.

Die Umgebungsvariable `STUDENT_GRADES` in `.env` listet alle gültigen
Jahrgangsstufen:

```
STUDENT_GRADES=[5,6,7,8,9,10,11,12]
```

## Alternative OAuth2/OIDC-Provider

Die Plattform ist nicht auf einen bestimmten SSO-Provider festgelegt. Jeder
OIDC-kompatible Provider kann verwendet werden, solange er beim Login einen
`groups`-Claim mit den Gruppenmitgliedschaften der Nutzerin liefert.

Die Standard-Endpunkt-Pfade sind auf IServ ausgelegt
(`/iserv/oauth/v2/auth` usw.). Für andere Provider können die Endpunkte in
`auth.yaml` überschrieben werden:

```yaml
oauth:
  base_url: https://sso.beispielschule.de
  client_id: ki-plattform
  redirect_uri: https://ki.beispielschule.de/auth/callback
  auth_url: "https://sso.beispielschule.de/oauth2/authorize"
  token_url: "https://sso.beispielschule.de/oauth2/token"
  userinfo_url: "https://sso.beispielschule.de/oauth2/userinfo"
```

Werden diese Felder nicht gesetzt, leitet die Plattform die URLs automatisch
aus `base_url` mit IServ-Pfaden ab — bestehende Konfigurationen müssen nicht
angepasst werden.

> **Hinweis:** Der Einsatz mit anderen Providern als IServ ist experimentell
> und noch nicht produktiv getestet. Das Client-Secret wird unabhängig vom
> Provider immer über `AUTH_ISERV_CLIENT_SECRET` in `.env` übergeben —
> der Variablenname bleibt aus Kompatibilitätsgründen unverändert.

## Automatische Kontoverwaltung

Nutzerkonten müssen nicht manuell gepflegt werden:

- **Anlegen:** Automatisch beim ersten Login.
- **Löschen:** Automatisch 90 Tage nach dem letzten Login (Cron-Job).
- **Budget-Tier-Wechsel:** Beim nächsten Monats-Reconcile, wenn der Jahrgang
  im SSO-System aktualisiert wurde.

Es gibt keine Admin-Oberfläche zum manuellen Anlegen oder Löschen von Konten.
Für eine vorzeitige manuelle Löschung (z. B. bei Abgang) steht das Skript
`scripts/cleanup_inactive_accounts.py` mit dem Parameter `--now` zur Verfügung —
siehe [Updates & Wartung](updates-und-wartung.md).
