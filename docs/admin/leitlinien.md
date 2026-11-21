# Leitlinien der Schule

Seit 0.50 kann die Schule eigene Rahmenwerke in der Bibliothek ablegen, die in den Curricula
vorkommen sollen, etwa die Nachhaltigkeitsziele (SDGs), das Weltethos oder das Medienkonzept.
Fachschaften verweisen im Curriculum auf sie, so wie auf die Leitperspektiven des
Bildungsplans, und der Curriculum-Assistent schlägt passende Aspekte vor.

Leitlinien pflegen **nur Admins**. Lesen dürfen alle, auch Schüler:innen.

## Aufbau

- Eine **Leitlinie** ist der Behälter, etwa „Nachhaltigkeitsziele“ mit dem Kürzel `SDG`.
- Ihre **Aspekte** sind die einzelnen Punkte, etwa „Klimaschutz“ mit dem Kürzel `SDG13`. Jeder
  Aspekt nennt das Kürzel seiner Leitlinie.

**Kürzel** sind Pflicht und je Art eindeutig. Leerzeichen entfallen, Kleinbuchstaben werden zu
Großbuchstaben. Über das Kürzel verweisen der Export und der Curriculum-Assistent auf eine
Leitlinie. Wählen Sie es deshalb dauerhaft:

- Das Kürzel einer Leitlinie lässt sich nicht mehr ändern, solange Aspekte es nennen.
- Ein exportiertes Curriculum (YAML) trägt die Kürzel. Beim Import in eine andere Instanz
  werden die Verweise nur aufgelöst, wenn es dort Leitlinien mit denselben Kürzeln gibt. Sonst
  bleibt der Verweis als Text stehen, und der Import meldet eine Warnung.

## Anlegen

1. Öffnen Sie **Bibliothek → Leitperspektiven**. Unten steht der Abschnitt **Leitlinien der
   Schule**.
2. **Leitlinie anlegen:** Titel, Kürzel und eine kurze Beschreibung.
3. Klappen Sie die Leitlinie auf und wählen Sie **Aspekt hinzufügen**. Das Kürzel der Leitlinie
   ist dann schon eingetragen. Geben Sie Titel, eigenes Kürzel und eine Beschreibung ein.

Die **Beschreibung eines Aspekts ist Pflicht.** Aus ihr entsteht der Suchvektor. Ein Aspekt nur
mit Titel wird in der Suche und im Chat kaum gefunden. Ein oder zwei Sätze genügen, etwa was
das Ziel an der Schule bedeutet.

Bearbeiten und Archivieren laufen wie bei jedem Baustein. Ein Aspekt, auf den Curricula
verweisen, wird beim Löschen archiviert.

## Wo Leitlinien erscheinen

- **Curriculum-Editor:** in der Auswahl nach `@` im Feld *Hinweise*, unter den
  Leitperspektiven, in eigener Farbe.
- **Abdeckung eines Curriculums** und Übersicht vor dem Veröffentlichen: welche Aspekte
  vorkommen. Nur zur Information, nicht als Pflicht.
- **Curriculum-Assistent:** Er fragt zu Beginn, ob das Curriculum Leitlinien berücksichtigen
  soll, und trägt Aspekte nach Zustimmung ein.
- **Schüler:innen** finden die Aspekte unter *Nachschlagen* auf der Seite ihres Fachs. Der
  Chat bezieht einen Aspekt ein, wenn eine Frage dazu passt (Vorab-Suche).
- Nicht in **Alle Bausteine**: Wie die Leitperspektiven stehen Leitlinien nur auf ihrer
  eigenen Seite.

## Nach dem Update auf 0.50

Damit der Curriculum-Assistent nach Leitlinien fragt, braucht er den neuen Prompt. Der Seed
ändert einen vorhandenen Assistenten nicht: Ersetzen Sie im Editor des Assistenten
„Curriculum-Entwurf“ den Prompt durch den Inhalt von `config/prompts/curriculum_assistent.md`.
Er gilt für neue Chats. Die Funktionen kennen die Leitlinien auch ohne den neuen Prompt. Eine
Migration ist nicht nötig.
