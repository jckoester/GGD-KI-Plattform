# Curriculum-Vorlagen einspielen (seit 0.62)

Mit **Vorlagen einspielen** legen Admins aus vielen Curriculum-YAMLs auf einmal **Entwürfe** an
— etwa aus Vorlagen, die ein KI-Programm über den MCP-Server aus den Beispielcurricula des
Landes geschrieben hat ([KI-Abos und MCP](ki-abos.md)). Die Fachschaften prüfen die Entwürfe,
passen sie an und veröffentlichen sie. Veröffentlichte Curricula ändert der Import nicht.

## Ablauf

1. **Bibliothek → Curricula**, oben rechts **Vorlagen einspielen** (nur für Admins sichtbar).
2. Dateien wählen (mehrere auf einmal, `.yaml`). Die Plattform prüft sie sofort, mit derselben
   Logik wie der Einzelimport — gespeichert wird dabei nichts.
3. Die Tabelle zeigt je Datei Fach, Klasse, Fassung, Quelle, Umfang, Fehler und Warnungen und,
   was entsteht:

   | Lage zu Fach, Klasse und Fassung | Es entsteht |
   |---|---|
   | noch kein Curriculum | ein neuer Entwurf |
   | genau ein veröffentlichtes, ohne offenen Entwurf | ein Entwurf, der es beim Veröffentlichen ersetzt |
   | schon ein Entwurf, eine frühere Datei desselben Durchgangs zur selben Stufe oder mehrere veröffentlichte (Bänder) | ein zusätzlicher Entwurf, der nichts ersetzt; im Titel steht „(Import TT.MM.JJJJ)“ |

4. **n Entwürfe anlegen** legt jede fehlerfreie Datei für sich an; eine fehlerhafte hält die
   übrigen nicht auf. Danach steht eine Liste mit Links zu den Entwürfen da.

Jeder Entwurf trägt Dateiname und Importdatum und zeigt den Hinweis, dass die Fachschaft ihn
prüft. Nach dem Veröffentlichen verschwindet der Hinweis; die Herkunft bleibt gespeichert. Steht
in der Datei ein Feld `quelle`, erscheint es unter dem Titel des Curriculums.

## Grenzen

- Höchstens **60 Dateien** je Durchgang, je Datei 200 KB, zusammen 12 MB. Der Anfragekörper
  bleibt damit unter `NGINX_MAX_BODY_SIZE` (Vorgabe `24m`, siehe
  [Upload-Grenzen](konfiguration.md#upload-grenzen)).
- Drossel: Eimer `curriculum_stapel` in `config/rate_limits.yaml`, Vorgabe 10 Aufrufe je
  10 Minuten (Prüfen und Anlegen je einer, also fünf Durchgänge). Der Einzelimport hat seinen
  eigenen Eimer `curriculum_import`.
- Dauer: 60 umfangreiche Dateien brauchen beim Prüfen Sekunden, beim Anlegen bis zu einer Minute
  — unter der Zeitgrenze des mitgelieferten nginx (300 s). Ein eigener Proxy davor braucht eine
  ebenso lange Lesezeit.

Fachschaften importieren einzelne Dateien über **Aus YAML importieren** in ihrem Fach. Den
Einzelimport haben Admins in jedem Fach und zusätzlich oben auf der Seite der Curricula.
