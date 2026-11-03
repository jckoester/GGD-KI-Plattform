# Vorschaumodus

Seit 0.29 können Lehrkräfte die Plattform als Schüler:in eines Jahrgangs und einer ihrer
Unterrichtsgruppen ansehen und ausprobieren (ADR-016, Hilfe: `docs/user/vorschau.md`). Diese
Seite erklärt, wie das gebaut ist und worauf eine neue Route oder ein neuer Schreibweg achten
muss.

## Ansatz: ein Token mit Schülerrolle

Das Vorschau-Token trägt `roles: ["student"]` und den gewählten Jahrgang als `grade`. Die echten
Rollen, der echte Jahrgang, die gewählte Gruppe, der Assistent aus dem Editor und der Ablauf der
Ausgangssitzung stehen im Merkmal `JwtPayload.preview` (`app.auth.vorschau.Vorschau`).

**Das Pseudonym bleibt das der Lehrkraft.** Budget, Kosten, Proxy-Schlüssel, Eigentum und
Audit-Spur bleiben bei ihr. Daraus folgt die Arbeitsteilung:

| Entscheidet über … | … in der Vorschau | Zuständig |
|---|---|---|
| Rollen (`require_role`, `"student" in roles`, Pädagogik, Modellfreigabe) | Schüler:in, von selbst | nichts zu tun |
| Mitgliedschaften (`group_memberships` je Pseudonym) | nur die gewählte Gruppe, als Schüler:in | `mitglied(pseudonym, rolle)` |
| Eigentum (eigene Assistenten, Knoten) | zählt nicht | `eigenes_zaehlt(pseudonym)` |
| Schreiben | gesperrt, außer Erlaubnisliste | `pruefe_schreibsperre` |
| Chats | nur Vorschau-Chats | `eigene_chats`, `darf_chat_sehen`, `darf_chat_fortsetzen` |
| Budget | echte Rollen (bezahlt wird aus dem Konto der Lehrkraft) | `/budget/me` |

Verworfen wurden zwei andere Wege: echte Rollen im Token behalten und überall einen
„effektiven Kontext“ abfragen (Inventur aller Rollenabfragen, eigene Schreibsperre), und ein
Zwillingskonto `<ID>_S` je Lehrkraft (zählte in Gruppen, Statistik, Krisen-Flags und Budget mit).

## Die Vorschau gilt je Anfrage

`get_current_user` ruft bei **jeder** Anfrage `vorschau.fuer_anfrage(payload)` auf und merkt sich
die Vorschau in einer `ContextVar` — auch „keine Vorschau“, damit nichts aus einer früheren
Anfrage desselben Tasks stehen bleibt. Die Helfer greifen nur, wenn das gefragte Pseudonym das
der Vorschau ist; Fragen nach anderen Personen bleiben echt.

Der Grund: Mitgliedschaften werden an rund dreißig Stellen gelesen, meist in Hilfsfunktionen,
die nur das Pseudonym bekommen. Den Benutzer überall durchzureichen hätte Signaturen quer durch
Kontext, Planung und Chat geändert.

## Mitgliedschaften

```python
from app.auth.vorschau import mitglied

select(GroupMembership.group_id).where(mitglied(pseudonym))            # alle eigenen
select(...).where(GroupMembership.group_id == g, mitglied(p, "teacher"))  # als Lehrkraft
```

In der Vorschau liefert `mitglied` nur die gewählte Gruppe, und die Frage nach `teacher` ist
immer falsch. `tests/unit/test_vorschau_mitgliedschaft_quelltext.py` verbietet
`GroupMembership.pseudonym ==` außerhalb des Helfers (Ausnahmen: Login-Abgleich, Admin-Gruppen,
Kontolöschung) und eine Rollenprüfung neben `mitglied()`.

⚠️ Eine Rollenprüfung nur über die Mitgliedschaft (`require_group_teacher`) ist erst durch den
Helfer vorschaufest. Drei Wege zum Ändern einer Unterrichtsgruppe prüfen keine Rolle — sie
wären ohne ihn in der Vorschau offen gewesen.

## Schreibsperre

`pruefe_schreibsperre` (in `get_current_user`) sperrt in der Vorschau jeden schreibenden Weg
(POST, PUT, PATCH, DELETE) mit 403 „In der Vorschau lässt sich nichts ändern.“, außer denen in
`ERLAUBT`. Geführt wird über die **Endpunkt-Funktion** (`scope["endpoint"]`), nicht über den
Pfad: Bei verschachtelt eingebundenen Routern fehlt in der Pfadvorlage das äußere Präfix.

Eine neue Route braucht deshalb nichts — sie ist in der Vorschau gesperrt, sobald sie
schreibt und eine Anmeldung verlangt. Soll sie in der Vorschau offen sein, gehört sie mit
Begründung in `ERLAUBT`. `tests/unit/test_vorschau_schreibsperre.py` prüft, dass jeder Name auf
der Liste einen echten Weg meint und kein schreibender Weg ohne Anmeldung auskommt.

## Chats

Ein Chat aus der Vorschau trägt `conversations.preview_context` (Jahrgang, Gruppe, Assistent,
Beginn). In der Vorschau sind nur solche Chats erreichbar, außerhalb erscheinen sie nur in der
eigenen Liste (`GET /conversations?vorschau=true`), lassen sich lesen und löschen, aber nicht
fortsetzen (409). Krisen-Flag, Zug-Auslöser und Vorab-Statistik werden übergangen
(`ohne_nebenwirkungen` im Chat-Router); das Krisen-Banner erscheint trotzdem. Der Löschlauf
nimmt Vorschau-Chats nach 30 Tagen.

## Lernstand

Aus der Vorschau darf kein persönlicher Lernstand (`node_engagement` je Pseudonym) entstehen.
Heute schreibt ihn niemand; wer einen Schreiber einführt, fragt `schreibt_lernstand(user)`.
`tests/unit/test_lernstand_schreiber.py` schlägt bei jeder neuen Datei an, die `node_engagement`
schreibt.

## Ein- und Austritt

- `POST /auth/vorschau` — nur Lehrkraft oder Admin, nur aus einer Browser-Sitzung, keine
  Verschachtelung; Gruppe nur eigene, aktuelle Unterrichtsgruppe; Assistent nur eigener.
  Ablauf `min(jetzt + 60 min, Ablauf der Sitzung)`. Audit `auth.preview_entered`.
- `DELETE /auth/vorschau` — stellt ein normales Token mit dem **alten** Ablauf aus und widerruft
  das Vorschau-Token. Nimmt auch ein **abgelaufenes** Vorschau-Token an
  (`JwtService.verify_ohne_ablauf`), einmal und nur solange die Ausgangssitzung gilt — sonst
  wäre mit der Vorschau auch die Sitzung der Lehrkraft vorbei. Audit `auth.preview_exited`.

## Oberfläche

`/auth/me` liefert `vorschau`; der Store `user` hält die Rollen aus dem Token, also `student`.
`VorschauBand.svelte` (App-Layout) zeigt Klasse, Gruppe und Restzeit und geht bei Ablauf von
selbst zurück; das App-Layout tauscht beim Laden ein abgelaufenes Vorschau-Token gegen die alte
Sitzung. Die Regeln für Band und Dialog stehen in `$lib/vorschau.js`.
