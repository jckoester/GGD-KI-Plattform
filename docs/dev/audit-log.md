# Audit-Log

Seit 0.28 hält die Tabelle `audit_log` sicherheitsrelevante Ereignisse fest: gescheiterte
Anmeldungen, Verwaltungsaktionen, Krisen-Flags, Ergebnisse der Löschläufe. Admins lesen sie
unter `/settings/audit`. Entscheidungen und Fristen: ADR-010 Teil 2 mit Nachtrag §2.5.

## Audit-Log oder Logger?

Beides protokolliert, aber für verschiedene Leser.

| | Audit-Log | Logger |
|---|---|---|
| **Frage** | Wer hat wann was getan oder versucht? | Was ist im Programm passiert, warum ging etwas schief? |
| **Leser** | Admins der Schule, ohne Zugang zum Server | Wer den Server betreibt oder den Fehler sucht |
| **Frist** | fest je Kategorie, löscht der Lauf `cleanup_audit_log` | wie die Log-Rotation des Servers |
| **Form** | feste Ereignisnamen, wenige Angaben | freier Text, Stacktraces |

**Ins Audit-Log** gehört eine Handlung mit Folgen für andere oder für die Sicherheit, die
später jemand nachvollziehen muss: Ein Admin gibt einen Assistenten frei, ändert ein Budget,
beendet Sitzungen; eine Anmeldung scheitert; ein Krisen-Flag entsteht. Ein Ereignis ist dort,
weil man es **suchen** will.

**In den Logger** gehört alles, was dem Betrieb hilft: Fehler, Zeiten, Zwischenstände, Abrufe
externer Dienste, Warnungen bei Konfigurationen. Auch Ereignisse aus dem Audit-Log dürfen
zusätzlich im Logger stehen, wenn sie dort beim Suchen nach Fehlern helfen.

Kein Kandidat fürs Audit-Log: reines Lesen (Seitenaufrufe, auch der Ansicht des Audit-Logs
selbst), gelungene Anmeldungen (stehen in `pseudonym_audit`), Ereignisse ohne Akteur und ohne
Folgen.

## Schreiben

Nur über `app/core/audit.py`. Ein Wächtertest (`test_niemand_schreibt_am_helfer_vorbei`)
schlägt an, wenn außerhalb des Helfers und des Modells `AuditLog(` oder
`INSERT INTO audit_log` steht.

```python
from app.core.audit import audit, audit_getrennt

# In der Transaktion der Änderung — geschrieben mit deren Commit, zurückgerollt mit ihr.
await audit(db, "admin", "assistant_approved", akteur=current_user,
            ziel=("assistant", assistant.id), daten={"audience": a.audience})
await db.commit()

# In eigener Sitzung — wenn der Anlass ein abgewiesener Request ist, dessen Transaktion
# nichts festschreibt. Wirft nie; ein Fehler beim Schreiben landet im Logger.
await audit_getrennt("auth", "login_failed", daten={"grund": "anmeldedaten"})
```

- **`audit`** für `admin`, `moderation`, `system`: Protokolliert wird, was geschah. Scheitert
  die Änderung, verschwindet auch der Eintrag.
- **`audit_getrennt`** für `auth`-Fehlschläge und für Änderungen, die nicht in der eigenen
  Datenbank liegen (LiteLLM-Proxy: Modell-Freischaltung, Budgets). Auf einem heißen Pfad über
  `im_hintergrund` aufrufen, wie es `_stepup_abgelehnt` und die Drossel tun.
- **`akteur`** nimmt die `JwtPayload` (Pseudonym und führende Rolle werden übernommen) oder ein
  Pseudonym als Text. Systemläufe lassen ihn weg.
- **`ziel`** ist ein Paar `(typ, kennung)`, etwa `("assistant", 12)` oder `("group", 7)`.

Prüfungen laufen **vor** dem Schreiben und werfen `ValueError`, auch bei `audit_getrennt`.
Ein falscher Ereignisname soll im Test auffallen, nicht im Betrieb still verschwinden.

## Ein neues Ereignis

1. Den Namen in `EREIGNISSE` (`app/core/audit.py`) unter seiner Kategorie eintragen. Ein
   unbekannter Name wirft.
2. Eine deutsche Bezeichnung in `BEZEICHNUNG` (`app/api/admin/audit.py`); ein Test verlangt sie.
3. Einen Test, der das Ereignis über die echte Schnittstelle auslöst
   (`tests/integration/test_audit_ereignisse_*.py` als Muster).
4. In der Liste der protokollierten Ereignisse in `docs/admin/datenschutz-betrieb.md` ergänzen.

Für ein Ereignis, das bei jeder abgewiesenen Anfrage entstünde, eine Drossel vorsehen.
`rate_limit_locked` schreibt höchstens einen Eintrag je Bereich, Person und Viertelstunde
(`app/ratelimit/dependency.py`).

## Was nie hineingehört

Keine Inhalte (ADR-010 §2.1): kein Chat-, Meldungs- oder Site-Text, kein Prompt, keine
Tokens, Passwörter, Cookies, Kontaktangaben, IP-Adressen. Dazu kein Benutzername bei
gescheiterten Anmeldungen: Ein vertippter Name ist oft das Passwort.

Der Helfer weist `daten` mit verdächtigen Schlüsseln ab (`text`, `inhalt`, `prompt`,
`token`, `kontakt`, `email` …), auch verschachtelt. Zahlen, Wahrheitswerte und Schlüssel auf
`_id` sind erlaubt, `max_tokens: 800` oder `mit_begruendung: true` also schon. Die Prüfung geht
nur über Schlüsselnamen. Sie fängt den naheliegenden Fehler, ersetzt aber nicht die Frage, was
man übergibt: `{"grund": nachricht.text}` ginge durch.

## Nur anhängen

Ein Trigger (`audit_log_nur_anhaengen`, Migration 0097) weist `UPDATE`, `DELETE` und
`TRUNCATE` ab. Ausnahme ist eine Transaktion, die vorher

```sql
SELECT set_config('audit.aufraeumen', 'on', true);   -- gilt nur bis zum Ende der Transaktion
```

gesetzt hat. Das tun genau zwei Stellen: der Aufräum-Lauf (`app/crons/audit_cleanup_service.py`)
und die Kontolöschung (`cleanup_inactive_accounts`). Sie setzen die Variable direkt danach
wieder auf `off`, damit nichts Weiteres in derselben Transaktion mitläuft.

Der Trigger ist kein Schutz gegen jemanden mit Datenbankzugang, der die Variable selbst
setzt. Er verhindert, dass die Anwendung versehentlich Einträge ändert. Ein eigener
Datenbankbenutzer ohne diese Rechte ist als Härtung vorgemerkt.

**Kontolöschung:** In `auth` und `moderation` wird `actor_pseudonym` auf `NULL` gesetzt,
`actor_role` bleibt. `admin` behält das Pseudonym bis zum Ende der Frist; das ist der Zweck
einer Revisionsspur.

## Tests

Unit-Tests schreiben nichts: Die Fixture `_audit_ohne_datenbank` in `tests/unit/conftest.py`
setzt `audit.SCHREIBEN = False`. Die Prüfungen laufen trotzdem.

Integrationstests schreiben in die Test-Datenbank: `_audit_in_die_testdatenbank` setzt
`audit.SITZUNGSFABRIK` auf deren Sitzungen. Ohne diese Fixture schrieb `audit_getrennt` über
`AsyncSessionLocal` in die Datenbank der Entwicklungsinstanz.

Wer im Test Zeilen löschen muss, setzt dafür die Sitzungsvariable wie oben
(`tests/integration/test_audit_ansicht.py`).
