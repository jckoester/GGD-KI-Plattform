# Hinweise auf Neuerungen

Seit 0.17 zeigt die Startseite Hinweise auf Neuerungen, die die eigene Rolle betreffen. Wer
einen Hinweis schließt, sieht ihn auf keinem Gerät wieder.

## Einen Hinweis schreiben

Die Hinweise stehen in **`backend/app/neuigkeiten/neuigkeiten.yaml`**. Die Datei kommt mit dem Release; die
Schule pflegt sie nicht. Ein Eintrag:

```yaml
- id: "0.17-fachbegriffe"        # eindeutig, nie wiederverwenden
  version: "0.17.0"
  datum: 2026-10-17              # ab wann
  rollen: [teacher]              # student, teacher, admin
  eintrag: planner               # optional: Navigationseintrag aus config/ui_levels.yaml
  titel: "Fachbegriffe im Stundenentwurf"
  text: >-
    Kurz, in der Sie-Form, aus Sicht der Nutzer:innen — nicht der Wortlaut des CHANGELOG.
  link: /help/unterrichtsplanung  # optional, eine Seite der Plattform
  bis: 2027-01-31                # optional: letzter Tag der Anzeige
```

Die **`id` nie wiederverwenden**: An ihr hängt „geschlossen". Ein neuer Hinweis mit alter `id`
bliebe bei allen unsichtbar, die den alten geschlossen haben.

Der Server prüft die Datei beim Start (`app/neuigkeiten/quelle.py`). Eine doppelte `id`, eine
unbekannte Rolle, ein unbekannter `eintrag`, ein Datum, das keins ist, oder ein Link nach außen
verhindern den Start. `tests/unit/test_neuigkeiten.py` prüft die ausgelieferte Datei.

## Wer einen Hinweis sieht

Entschieden wird an einer Stelle, `sichtbar()` in `app/neuigkeiten/quelle.py`:

1. Eine der eigenen Rollen steht in `rollen`. Rollen sind additiv: Ein Admin sieht auch die
   Hinweise für Lehrkräfte.
2. Die Person hat den Hinweis nicht geschlossen (`user_preferences`, Schlüssel
   `neuigkeiten_gelesen`).
3. Der Hinweis ist nicht älter als das Konto (`pseudonym_audit.created_at`). Wer neu dazukommt,
   wird nicht mit alten Neuigkeiten begrüßt.
4. `bis` ist nicht überschritten.
5. Mit `eintrag`: Der Navigationseintrag liegt in der eigenen Darstellungsstufe. Den Hinweis zum
   Stundenassistenten bekommt also nur, wer die Unterrichtsplanung sieht. Kennt die
   Konfiguration der Schule den Eintrag gar nicht, erscheint der Hinweis trotzdem — lieber einer
   zu viel als ein verschluckter.

## Schnittstelle

- `GET /neuigkeiten` — die sichtbaren Hinweise, neueste zuerst: `id`, `titel`, `text`, `link`.
- `POST /neuigkeiten/{id}/gelesen` — schließt den Hinweis. Ein zweiter Aufruf ändert nichts;
  eine unbekannte `id` ergibt 404.

Die Startseite (`/welcome`) zeigt die Hinweise oben als `InfoBanner` mit Schließen-Knopf.

## Datenschutz

`neuigkeiten_gelesen` liegt in `user_preferences` und wird mit dem Konto gelöscht (Lösch-Cron,
90 Tage ohne Anmeldung). Gespeichert werden nur Kennungen von Hinweisen.

## Beim Release

Zur Release-Vorbereitung gehört die Frage: **Gibt es eine Neuerung, auf die Nutzer:innen
hingewiesen werden sollten?** Wenn ja, einen Eintrag schreiben. Nicht jede Änderung braucht
einen — nur was sich in der täglichen Arbeit bemerkbar macht oder etwas von den Nutzer:innen
verlangt (etwa einen eigenen Assistenten anzupassen).

`datum` eines neuen Eintrags ist der Tag des Releases. Ein früheres Datum — etwa der Tag, an
dem die Neuerung gebaut wurde — verbirgt den Hinweis vor allen, die ihr Konto dazwischen
angelegt haben.
