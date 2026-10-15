# Vorab-Suche beobachten

*Seit 0.16.* Unter `/statistics/vorab` (Rollen `admin` und `statistics`) steht, was die
Plattform zu den Chat-Nachrichten aus dem Wissensspeicher der Schule herausgesucht hat — und
ob das Modell angebotene Einträge nachgeschlagen hat.

## Was die Vorab-Suche tut

Zu jeder Nachricht sucht die Plattform passende Einträge (Fachbegriffe, Stoffsteckbriefe,
Methoden- und Operatorenblätter) und legt sie dem Modell auf zwei Stufen vor:

- **sicher** — höchstens fünf Einträge, die sehr nah an der Nachricht liegen oder beim Namen
  genannt werden. Ihr **Inhalt** steht im Prompt; das Modell glaubt ihn. Diese Einträge stehen
  auch in der Zeile „Kontext" unter der Antwort.
- **angeboten** — höchstens fünf weitere, die im Satz vorkommen oder etwas weiter entfernt
  liegen. Im Prompt steht nur ihr **Titel** mit dem Hinweis, dass das Modell den Inhalt mit
  seiner Suche holen kann. Unter der Antwort erscheinen sie nur, wenn es das tut.

## Die Zahlen

**Je Woche** zählen die Spalten **Nachrichten**, nicht Einträge:

| Spalte | Bedeutung |
|---|---|
| Nachrichten | Antworten im Chat (Vorschau-Chats aus dem Assistenten-Editor zählen nicht) |
| mit sicherem Treffer | mindestens ein Eintrag als Inhalt im Prompt |
| mit Angebot | mindestens ein Titel angeboten |
| nachgeschlagen | Anteil der Nachrichten mit Angebot, in denen mindestens ein angebotener Eintrag im Suchergebnis des Modells stand |
| davon ohne sicheren Treffer | dieselbe Quote, nur für Nachrichten **ohne** sicheren Treffer |
| Suchen ohne Angebot | das Modell suchte selbst, obwohl nichts angeboten war |

⚠️ **„Nachgeschlagen" heißt nicht „gezielt geholt".** Gezählt wird, ob der angebotene Eintrag
im Suchergebnis derselben Antwort stand. Sucht das Modell nach etwas anderem und bringt die
Suche ihn mit, zählt er auch. Die Quote ist deshalb keine Trefferquote.

**Lesen Sie die Quote ohne sicheren Treffer.** Steht schon ein Eintrag als Inhalt im Prompt,
schlägt das Modell ein Angebot daneben fast nie nach — es hat ja schon, was es braucht. Über
alle Nachrichten gerechnet sähe die Quote deshalb viel schlechter aus, als das Angebot
arbeitet. In der Messung vor der Einführung (gpt-oss) wurden Angebote ohne sicheren Treffer in
rund 60 % der Fälle nachgeschlagen, mit sicherem Treffer daneben so gut wie nie.

**Je Eintrag**: wie oft er sicher vorgelegt, wie oft angeboten und wie oft davon nachgeschlagen
wurde. Das Fach ist das des Eintrags; der Filter oben gilt dem Fach des Chats. Einträge, die
Sie nicht lesen dürfen (private Einträge anderer), stehen ohne Titel da.

## Was man daraus tut

- **Oft angeboten, nie nachgeschlagen:** meist ein Titel oder Suchbegriff, der zugleich ein
  Alltagswort ist („Stoff", „Probe"). Das kostet wenig — ein liegengelassener Titel verbiegt
  die Antwort nicht —, ist aber der Ort, an dem die Fachschaft Suchbegriffe aufräumt: Ein
  Suchbegriff soll ein zweiter Name sein, kein Themenwort (siehe
  [Fachbegriffe pflegen](../user/fachbegriffe-pflegen.md)).
- **Quote ohne sicheren Treffer sinkt deutlich:** ein Hinweis, dass ein anderes Modell oder
  eine geänderte Modellkonfiguration seltener sucht.
- **Viele Suchen ohne Angebot:** Das Modell findet Einträge, die die Vorab-Suche nicht
  anbietet — ein Anlass, die Schwellen nachzumessen (Entwicklungs-Doku
  `docs/dev/kontextsuche.md`).

Der Export als CSV (je Tabelle) enthält die Rohzahlen für eigene Auswertungen.

## Datenschutz

Die Tabelle `vorab_statistik` enthält **keine personenbezogenen Daten**: kein Pseudonym, keinen
Bezug zu Konversation oder Nachricht — nur Zählerstände je Kalenderwoche, Eintrag, Stufe, Fach
des Chats und Modell. Sie wird nicht automatisch gelöscht; Zeilen eines gelöschten Eintrags
oder Fachs verschwinden mit ihm. Siehe [Datenschutz & Betrieb](datenschutz-betrieb.md).
