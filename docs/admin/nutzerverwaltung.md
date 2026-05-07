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
- Client-Secret in `AUTH_ISERV_CLIENT_SECRET` in `config/.env` eintragen

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

## SSO-Gruppenimport: Unterrichtsgruppen

Wenn der SSO-Provider Gruppen für Fachschaften, Schulklassen und
Unterrichtsgruppen liefert, importiert die Plattform diese automatisch beim
Login. Dafür müssen die Gruppennamen in `auth.yaml` unter `sso.groups` als
Regex-Muster konfiguriert sein.

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

## Unterrichtsgruppen manuell anlegen

Lehrkräfte können Unterrichtsgruppen auch manuell anlegen, wenn der SSO-Provider
sie nicht automatisch liefert. Das Verhalten wird über das Flag
`allow_manual_teaching_groups` in `auth.yaml` gesteuert:

| Wert | Verhalten |
|------|-----------|
| `true` (Standard) | Lehrkräfte sehen Vorschläge in der Sidebar und können bestätigen oder ablehnen |
| `false` | Vorschläge werden nicht angezeigt; `POST /api/groups/teaching` gibt HTTP 403 zurück |

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
> Provider immer über `AUTH_ISERV_CLIENT_SECRET` in `config/.env` übergeben —
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
