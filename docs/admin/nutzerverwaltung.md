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

## Jahrgangsklassen

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
