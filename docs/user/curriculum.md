# Schulcurriculum

*(nur für Lehrkräfte)*

Das Schulcurriculum ist die schuleigene Umsetzung des Bildungsplans: Es legt fest, in
welcher Reihenfolge, mit welchem Zeitansatz und mit welchen Schwerpunkten die Kompetenzen
eines Fachs unterrichtet werden.

> **Bildungsplan ≠ Curriculum.** Der **Bildungsplan** ist die Landesvorgabe — er steht fest
> und lässt sich hier nicht ändern. Das **Curriculum** ist eure Fachschaftsarbeit darauf:
> Kapitel, Lernsequenzen, Konkretisierungen, Material.

Du erreichst Curricula über **Bibliothek → Curricula** oder direkt von der Fachseite aus. Oben
verlinkt ein Curriculum den [Jahresverlaufsplan](jahresverlaufsplan.md) seiner Stufe.

## Die Liste

Die Liste ist nach dem Bildungsplan gegliedert: je **Fach** die **Fassungen** des Bildungsplans,
darin die **Bänder** des Plans („Klassen 5/6“, „Klassen 12/13 (Leistungsfach)“) und in jedem
Band die Curricula, die dazu gehören.

- Oben wählst du **Meine Fächer**, **Alle Fächer** oder ein **bestimmtes Fach**. Bei „Meine
  Fächer“ bietet auch die Fachauswahl nur deine Fächer an.
- Fächer und Fassungen lassen sich einklappen. Zuerst stehen die geltenden Fassungen, dann die
  kommende; frühere Fassungen, an denen noch Curricula hängen, sind eingeklappt.
- In deinen eigenen Fächern siehst du auch Bänder ohne Curriculum — dort fehlt noch eines.
- Ein Entwurf, der ein veröffentlichtes Curriculum ersetzen soll, steht daneben mit
  „ersetzt …“.
- Am Kopf eines Bands führt **IK-Abdeckung im Band**, am Kopf einer Fassung **PK-Abdeckung der
  Fassung** zur Abdeckung über mehrere Curricula (siehe [Abdeckung](#abdeckung)).

---

## Wer darf was

Ein Curriculum gehört der **Fachschaft**, nicht einer einzelnen Person. Solange es ein
**Entwurf** ist, bearbeitet es die Fachschaft; lesen können es alle Lehrkräfte, etwa um sich
zwischen Fächern abzustimmen. Mit dem **Veröffentlichen** gilt es für alle.

| | Entwurf | Veröffentlicht |
|---|---|---|
| **Ansehen** | alle Lehrkräfte | alle Lehrkräfte |
| **Bearbeiten** | Mitglieder der Fachschaft, Admins | Fachvorsitz und Admins\* |
| **Veröffentlichen** | Fachvorsitz und Admins\* | — |
| **Löschen** | wer den Entwurf angelegt hat, Fachvorsitz, Admins | Fachvorsitz und Admins\* |
| **Als Entwurf kopieren** | — | Mitglieder der Fachschaft, Admins |

\* **Fachvorsitz** gibt es nur, wenn deine Schule dafür eine Gruppe eingerichtet hat. Dann
gehört dazu, wer zu dieser Gruppe **und** zur Fachschaft gehört. Ohne diese Gruppe dürfen das
alle Mitglieder der Fachschaft.

Wenn du ein Curriculum nur lesen kannst, obwohl es dein Fach ist, fehlt dir
wahrscheinlich die Fachschaftsmitgliedschaft — das klärt die Administration. Ein
veröffentlichtes Curriculum überarbeitest du ohne Fachvorsitz über **„Als Entwurf kopieren“**
(siehe unten).

---

## Ein Curriculum anlegen

**Wissen → Curricula → Neu**, dann zwei Angaben:

1. **Bildungsplan** des Fachs auswählen. Damit steht auch die Fassung fest (z. B. BP 2016
   oder die überarbeitete Fassung V2).
2. **Jahrgangsstufe oder Stufenband** eintragen — freie Eingabe: `7`, `7/8`, `5–6`.

Den Rest baust du im Editor auf. Das neue Curriculum ist ein **Entwurf** — siehe nächster
Abschnitt. Legst du für dieselbe Stufe und Fassung noch einmal eins an, öffnet sich dein
vorhandener Entwurf; ein Doppel entsteht nicht.

**Oberstufe: das Band wählen.** In der Kursstufe gibt es zu denselben Klassen mehrere Bänder
im Bildungsplan — Basis- und Leistungsfach, in Physik auch zwei Basisfach-Schwerpunkte. Dann
wählst du im Editor unter **Band im Bildungsplan**, wofür das Curriculum gilt. Bis dahin steht
es in der Liste unter „Band nicht zugeordnet“, und die Abdeckung zählt die Kompetenzen aller
dieser Bänder.

**Mit dem Assistenten:** Der Assistent **Curriculum-Entwurf** legt ein Curriculum auch für dich
an und baut es mit dir auf (siehe [Mit dem Assistenten arbeiten](#mit-dem-assistenten-arbeiten)).

**Für eine Fassung, die erst später gilt:** Steht neben dem Bildungsplan „gilt ab 2027/28“,
ist das die kommende Fassung. Du kannst dein Curriculum dafür schon jetzt schreiben —
Kompetenzen, Abdeckung und Export arbeiten mit ihr wie mit der geltenden. In Suche und
Assistenten erscheint die kommende Fassung erst, wenn sie gilt.

> Erscheint dein Fach nicht in der Auswahl, ist sein Bildungsplan in dieser Installation
> noch nicht eingelesen. Das ist eine Aufgabe der Administration, keine Einstellung, die
> du ändern kannst.

### Aus einer YAML-Datei importieren

Ein Curriculum, das als YAML vorliegt — aus dem Export einer anderen Plattform oder von einem
KI-Programm entworfen (siehe [KI-Programme verbinden](profil.md#ki-programme-verbinden)) —,
holst du über **Aus YAML importieren** herein — in der Liste der Curricula eines Fachs oder auf
der Fachseite im Reiter Curricula. Den Knopf sieht, wer in der Fachschaft des Fachs ist, und
Admins (in jedem Fach, dazu oben auf der Seite der Curricula; das Fach steht in der Datei).

1. Datei wählen oder den Text einfügen.
2. **Prüfen.** Die Vorschau zeigt Titel, Klasse, Fassung, die Kapitel mit Stunden und Umfang —
   und was nicht passt:
   - **Fehler** (rot) mit der Stelle in der Datei, etwa „Kapitel 3, Lernsequenz 2: `std` ist
     keine Zahl“. Mit Fehlern lässt sich nichts anlegen.
   - **Hinweise** (gelb): Kompetenznummern oder Verweise, die es in dieser Plattform nicht
     gibt, unbekannte Felder. Der Import geht trotzdem; was nicht aufgelöst wird, bleibt ohne
     Verknüpfung.
3. Gibt es zu Fach, Klasse und Fassung schon ein veröffentlichtes Curriculum, wählst du:
   **ersetzt beim Veröffentlichen** dieses Curriculum (vorausgewählt) oder **neuer Entwurf,
   der nichts ersetzt**. Beim Ersetzen wandern die Unterrichtseinheiten an Kapiteln mit
   gleichem Titel mit, wie bei „Als Entwurf kopieren“.
4. **Als Entwurf anlegen** — der Editor öffnet sich.

Es entsteht **immer ein Entwurf**. Vorhandene Curricula ändert der Import nicht; sichtbar für
alle wird der Entwurf erst, wenn ihr ihn veröffentlicht. Änderst du nach dem Prüfen den Text
oder die Wahl, prüfst du neu.

Verweise auf Bausteine, die du nicht lesen darfst, bleiben als Text ohne Link stehen.

Steht in der Datei eine **Quelle** (Feld `quelle`, etwa „Beispielcurriculum Physik Gymnasium
Klassen 7–8 (ZSL, Fassung V3.0)“), zeigt die Vorschau sie, und das Curriculum trägt sie unter
seinem Titel — auch nach dem Veröffentlichen, im Export und in einer Kopie. Ein KI-Programm, das
einen Entwurf aus einem Beispielcurriculum schreibt, füllt das Feld von sich aus.

### Entwürfe aus Vorlagen

Die Administration kann Vorlagen für viele Fächer auf einmal einspielen, etwa aus den
Beispielcurricula des Landes. Daraus entstehen **Entwürfe** in deinem Fach, oben mit dem Hinweis
„Aus einer Vorlage importiert … — die Fachschaft prüft und passt an, bevor sie veröffentlicht.“
Ein solcher Entwurf ist ein Angebot: Ihr bearbeitet ihn wie jeden anderen, veröffentlicht ihn
oder löscht ihn. Gab es zur Stufe schon ein veröffentlichtes Curriculum, ersetzt der Entwurf es
erst, wenn ihr ihn veröffentlicht. Gab es schon einen Entwurf, steht beim neuen das Importdatum
im Titel, damit ihr beide auseinanderhaltet.

---

## Entwurf und Veröffentlichen

Ein neues Curriculum ist zunächst ein **Entwurf**: In der Liste trägt es die Marke „Entwurf“,
in Ansicht und Editor steht ein Hinweis. Lesen können den Entwurf alle Lehrkräfte (seit 0.52),
bearbeiten nur die Mitglieder der Fachschaft und Admins. Wer ihn nur liest, sieht oben
„Entwurf — nur lesen“ und keine Knöpfe zum Bearbeiten; exportieren geht. In Suche, Chat und
Jahresplanung erscheint ein Entwurf nicht — für niemanden, auch nicht für die Fachschaft. Ein Entwurf läuft nicht ab; die Liste zeigt, wann er zuletzt geändert wurde.

**Veröffentlichen** — der Knopf steht oben rechts in Ansicht und Editor. Vorher zeigt eine
Übersicht, was auffällt: Stunden, nicht verknüpfte Kompetenzen, als veraltet markierte
Kompetenzen, fehlende Begriffe. Sie warnt nur; veröffentlichen kannst du trotzdem. Danach sehen
alle das Curriculum, und es ist in der Jahresplanung wählbar. Darfst du nicht veröffentlichen,
steht an der Stelle des Knopfs, wer es darf.

**Je Fach, Klassenstufe und Bildungsplan-Fassung gilt ein Curriculum.** Gibt es schon ein
veröffentlichtes, wählst du in der Übersicht, welches der Entwurf **ersetzt** — wie bei „Als
Entwurf kopieren“: Das alte wird archiviert, Einheiten dieses Schuljahrs und Jahresverlaufspläne
wandern an die Kapitel gleichen Titels. Ausgenommen sind verschiedene Bänder.

Im Export steht bei einem Entwurf unter dem Titel „Entwurf, Stand …“.

### Ein veröffentlichtes Curriculum überarbeiten

**„Als Entwurf kopieren“** legt eine Kopie an, die du in Ruhe überarbeitest. Das Original
gilt so lange weiter. Pro Curriculum gibt es höchstens einen solchen Entwurf — gibt es ihn
schon, führt der Knopf als **„Zum Entwurf“** dorthin.

Wird die Kopie veröffentlicht, **ersetzt** sie das Original:

- Das Original wird archiviert.
- Unterrichtseinheiten **dieses Schuljahrs**, die an einem Kapitel des Originals hängen,
  wandern auf das entsprechende Kapitel der Kopie.
- Hast du in der Kopie ein Kapitel gelöscht, behalten die Einheiten daran das alte Kapitel.
  Die Übersicht vor dem Veröffentlichen nennt Gruppe und Kapitel; in der Planung erscheint
  bei solchen Einheiten ein Hinweis, damit die Lehrkraft ein neues Kapitel wählt.
- Einheiten früherer Schuljahre bleiben, wie sie sind.

### Einen Entwurf löschen

Einen Entwurf löschen die Person, die ihn angelegt hat, der Fachvorsitz und Admins — nicht
jedes Mitglied der Fachschaft. Kapitel und Lernsequenzen im Entwurf löscht jedes Mitglied
im Editor wie gewohnt.

### Rückgängig

Vor jedem Speichern merkt sich der Editor den Stand. **Rückgängig** im Kopf des Editors stellt
den Stand vor der letzten Speicherung wieder her — Texte, Einträge, Kompetenzen, gelöschte und
neu angelegte Kapitel und Lernsequenzen. Mehrmals geklickt, geht es Speicherung für Speicherung
zurück, bis zu 30 Mal. Der Tooltip zeigt, von wann die letzte Speicherung ist und ob sie von
dir, jemand anderem aus der Fachschaft oder dem Assistenten stammt.

- Rückgängig geht nur ohne ungespeicherte Änderungen — erst speichern oder abbrechen.
- Es nimmt die **ganze** letzte Speicherung zurück, auch wenn sie jemand anderes gemacht hat.
- Zurückgenommen wird der Inhalt, nicht das Veröffentlichen: Ein veröffentlichtes Curriculum
  bleibt veröffentlicht.
- Ein Zurücknehmen lässt sich nicht wiederum zurücknehmen.

---

## Aufbau: Kapitel, Lernsequenzen, Einträge

```
Curriculum  (Fach + Jahrgangsband)
└── Kapitel            z. B. „Kreise und Körper"        · Stundenansatz
    └── Lernsequenz    z. B. „Satz des Pythagoras"      · Stundenansatz
        └── Eintrag    Kompetenzen + Konkretisierung + Begriffe + Fachmethoden + Hinweise + Material
```

**Kapitel** gliedern das Schuljahr, **Lernsequenzen** die Kapitel. Ein Kapitel lässt sich
über den Pfeil im Kopf **einklappen** — bei langen Curricula die schnellste Art, den
Überblick zu behalten.

Die **Stundenansätze** addiert die Ansicht mit; oben siehst du die Gesamtsumme. So merkst
du früh, wenn die Planung nicht ins Schuljahr passt.

### Rahmen

Über den Kapiteln steht der Abschnitt **Rahmen**. Dort hält die Fachschaft fest, was für das
ganze Curriculum gilt:

- **Wochenstunden** je Klassenstufe des Bands (halbe Stunden mit Komma, etwa „1,5“)
- **Lehrwerk**
- **Beschlüsse der Fachschaft**, etwa Lektüren, Pflichtversuche, Exkursionen
- **Schwerpunkte**, für die die Fachschaft die freie Zeit nutzt
- **Absprachen in der Fachschaft**, etwa zu Leistungsnachweisen oder zum Methoden- und
  Medienkonzept — Absprachen mit anderen Fächern stehen am Kapitel (siehe
  [Absprachen mit anderen Fächern](#absprachen-mit-anderen-fächern))

Die Textfelder verstehen Markdown, also auch Aufzählungen.

> **Das Lehrwerk ist eine Angabe, kein Inhalt.** Die Plattform kennt nur den Titel, nicht
> das Buch. Auch der Curriculum-Assistent weiß nicht, was in welchem Kapitel des Lehrwerks
> steht, und plant deshalb nicht von selbst danach. Soll er sich daran halten, nenne ihm
> die Kapitel und ihre Reihenfolge.

Sobald jede Stufe ihre Wochenstunden hat, zeigt der Rahmen, wie viele Stunden **verplanbar**
sind: 30 je Wochenstunde, bei einem zweistündigen Fach also 60 im Jahr. Den Rest des Schuljahres
lässt das Curriculum bewusst frei. Daneben steht, wie viele Stunden die Kapitel schon verplanen.

Im Editor ist der Rahmen aufgeklappt, solange er leer ist. In der Ansicht erscheint er nur, wenn
etwas angegeben ist. Im Export steht er als Abschnitt „Rahmen“ vor dem ersten Kapitel.

---

## Kompetenzen verknüpfen

In jedem Eintrag verknüpfst du Kompetenzen des Bildungsplans:

- **IK** — inhaltsbezogene Kompetenzen (was inhaltlich behandelt wird)
- **PK** — prozessbezogene Kompetenzen (welche Arbeitsweisen geübt werden)

Beide Felder durchsuchen den Bildungsplan **deines Fachs in der passenden Fassung** — du
musst dich also nicht darum kümmern, ob eine Kompetenz zur richtigen Edition gehört.

**„Partiell" ankreuzen**, wenn eine Kompetenz an dieser Stelle nur teilweise bedient wird.
Das ist kein Schönheitsfehler, sondern die ehrliche Auskunft: Dieselbe Kompetenz taucht
dann an mehreren Stellen auf, und keine behauptet, sie allein abzudecken.

### Querverweise in andere Fächer

An vielen Kompetenzen nennt der Bildungsplan selbst, wo ein **anderes Fach** anschließt. Hat
eine verknüpfte Kompetenz solche Verweise, stehen hinter ihrer Nummer kleine Marken mit dem
Kürzel des Fachs in seiner Farbe, etwa **PH** oder **BNT**. Ein Klick klappt die Liste auf:

- welche Kompetenz oder welcher **Bereich** des anderen Fachs gemeint ist, mit Stufen und
  Nummer — der Bildungsplan verweist oft auf einen ganzen Bereich, nicht auf eine einzelne
  Kompetenz;
- **wo das andere Fach die Stelle behandelt**: in welchem Curriculum und Kapitel, Entwürfe als
  solche gekennzeichnet. Steht dort „in keinem Curriculum … verknüpft“, hat die andere
  Fachschaft die Stelle noch nicht eingeplant — ein guter Anlass für eine Absprache.

Die Verweise kommen aus dem Bildungsplan und lassen sich nicht bearbeiten. Du siehst sie in
beide Richtungen: auch, wenn nur das andere Fach auf deins verweist. Gilt die Fassung des
anderen Fachs erst später, steht „ab Schuljahr …“ dabei. Dieselben Marken findest du in der
Bibliothek unter **Bildungspläne** und — beim Bearbeiten — unter den gewählten Kompetenzen.

Eigene Bezüge, die der Bildungsplan nicht nennt, trägst du weiter in den **Hinweisen** ein
(übernächster Abschnitt). Was ihr mit der anderen Fachschaft vereinbart habt, hältst du als
**Absprache** am Kapitel fest — im Editor steht dafür an jeder Fundstelle **Absprache anlegen**.

### Absprachen mit anderen Fächern

> Wie die Fächer über alle Klassenstufen zusammenhängen, mit Absprachen, Querverweisen und den
> Jahresverlaufsplänen, zeigt die [Vernetzung der Fächer](vernetzung.md). Du erreichst sie oben
> im Curriculum und an jedem Kapitel über „Vernetzung“.

Am Kapitel hältst du fest, was deine Fachschaft mit einer anderen vereinbart hat, etwa
„Bruchrechnung in Mathematik vor Dichte in Physik“. Im Editor steht unter der Einleitung jedes
Kapitels **Absprachen mit anderen Fächern** → **Absprache hinzufügen**:

1. **Fach** — tipp die ersten Buchstaben oder das Kürzel.
2. Wahlweise **Curriculum** und **Kapitel** des anderen Fachs. Curricula deiner Stufe stehen
   oben, die Fassung steht in Klammern. Ohne Kapitel gilt die Absprache dem ganzen Fach.
3. **Art**:
   - **vorher** — das Kapitel des anderen Fachs kommt zuerst;
   - **gleichzeitig** — etwa in denselben Wochen;
   - **danach** — das andere Kapitel kommt später;
   - **abgestimmt** — inhaltlich abgestimmt, ohne Zeitpunkt, etwa „Begriffe einheitlich“.
   Die ersten drei brauchen ein Kapitel, „abgestimmt“ braucht einen Text.
4. **Was vereinbart ist** — ein, zwei Sätze. **Übernehmen**, dann das Curriculum speichern.

Die andere Fachschaft sieht die Absprache an ihrem Kapitel, mit „eingetragen von der
Fachschaft …“ und der Art aus ihrer Sicht: Dein „vorher“ steht bei ihr als „kommt danach“.
Zustimmen muss sie nicht. Will sie die Absprache auch selbst festhalten, legt sie mit
**Gegenabsprache anlegen** die passende an — danach steht bei beiden **beidseitig**, und die
Absprache erscheint nur noch einmal. Formuliert sie anders, steht ihr Text darunter.

Ersetzt eine Fachschaft ihr Curriculum, bleiben die Absprachen am neuen Kapitel gleichen
Titels. Entwürfe der anderen Fachschaft sind gekennzeichnet; Schüler:innen sehen keine.

**Passt das zu den Jahresverlaufsplänen?** Haben beide Fächer für das laufende Schuljahr einen
[Jahresverlaufsplan](jahresverlaufsplan.md), prüft die Plattform zeitliche Absprachen: Unter der
Absprache steht „Passt zu den Jahresverlaufsplänen“ oder, rot, „Laut Jahresverlaufsplänen nicht
eingehalten“ — jeweils mit Klassenstufe und Kalenderwochen beider Kapitel. Dabei gilt:

- **vorher** ist eingehalten, wenn das andere Kapitel spätestens in der Woche endet, in der
  dieses beginnt; **danach** umgekehrt;
- **gleichzeitig** ist eingehalten, wenn sich die Wochen überschneiden;
- liegen die Kapitel in verschiedenen Klassenstufen, entscheiden die Stufen („Kl. 7 vor Kl. 8“),
  auch ohne Plan;
- fehlt ein Plan und liegen beide in derselben Stufe, steht nichts dabei — es lässt sich nicht
  sagen.

Die Prüfung warnt nur. Stammt eine Woche aus einem Entwurf des Plans, steht „(Entwurf)“ dabei.

### Hinweise, Leitperspektiven und Leitlinien

Im Feld **Hinweise** schreibst du Freitext. Mit `@` verweist du zusätzlich auf
**Leitperspektiven** und ihre Aspekte, mit `#` auf Kompetenzen **anderer Fächer** — das ist
der Weg, fächerverbindende Bezüge sichtbar zu machen.

Hat die Schule eigene **Leitlinien** hinterlegt, etwa die Nachhaltigkeitsziele oder das
Weltethos, stehen sie in derselben Auswahl nach `@`, unter den Leitperspektiven. Du verweist
auf die Leitlinie als Ganzes oder auf einen ihrer Aspekte. Im Curriculum erscheinen sie in
einer eigenen Farbe, damit Bildungsplan und Schule unterscheidbar bleiben.

Auch den **Leitfaden Demokratiebildung** findest du dort, unter den Leitperspektiven. Du
verweist auf den Leitfaden als Ganzes, auf einen Baustein, einen Themenblock oder eine
Kompetenz. Ohne Suchtext zeigt die Auswahl nur Bausteine und Themenblöcke. Tippst du weiter,
etwa „streiten“ oder „B1.T2“, erscheinen auch die passenden Kompetenzen. Im Curriculum steht
dann zum Beispiel „LFDB B1.T2: Richtig streiten lernen“.

### Material

Im Feld **Material** steht Freitext, Links — und mit `@` Verweise auf Bausteine aus dem
[Bibliothek](bibliothek.md): Arbeitsblätter, Aufgaben, Präsentationen, Methodenblätter
und fachliche Konzepte.

Bildungsplan-Kompetenzen erscheinen hier bewusst **nicht** — dafür gibt es die IK- und
PK-Felder. Zwei Wege für dieselbe Verknüpfung wären nur verwirrend.

### Abdeckung

Über der Tabelle steht aufklappbar die **Abdeckung**: Wie viele inhaltsbezogene Kompetenzen
des Bands das Curriculum verknüpft, welche nur partiell und welche gar nicht — und wie oft jede
prozessbezogene Kompetenz gefördert wird. Gezählt wird, was in den Spalten IK und PK steht,
nicht die Verweise in den Hinweisen.

- **Zum Band** gehören die Kompetenzen, die der Bildungsplan unter der Überschrift des Bands
  führt, etwa „Klassen 9/10“. Ein Curriculum für Klasse 9 sieht also die Kompetenzen des Bands
  9/10. In der Oberstufe zählt das gewählte Band (Basis- oder Leistungsfach).
- Fehlt eine Kompetenz, steht dabei, ob ein **anderes veröffentlichtes Curriculum** desselben
  Bands sie verknüpft — etwa das für Klasse 10.
- Zwei Links führen weiter: **Abdeckung über alle Curricula des Bands** und, bei den
  prozessbezogenen Kompetenzen, **Über alle Curricula der Fassung**.
- **Aus einem anderen Fach:** Erscheint dieser Abschnitt, hängt das Curriculum an Kompetenzen
  eines anderen Fachs — meist ein Überbleibsel eines alten Imports. Ersetze sie im Editor oder
  bitte die Schul-IT um die Reparatur.
- **Leitlinien der Schule:** Je Leitlinie steht, welche Aspekte in welchen Lernsequenzen
  vorkommen und welche nicht. Das ist eine Information, keine Pflicht — eine Leitlinie muss
  nicht in jedem Curriculum stehen. Auch die Übersicht vor dem Veröffentlichen nennt es.
  Wo eine Leitlinie oder Leitperspektive in **allen** Curricula vorkommt, zeigt die
  [Übersicht auf der Seite Leitperspektiven](bibliothek.md#wo-kommt-eine-leitperspektive-im-unterricht-vor).
- Die Abdeckung zeigt den **gespeicherten** Stand; im Editor lädt sie nach dem Speichern neu.

### Abdeckung über das Band

Ein Band umfasst oft zwei oder drei Klassenstufen, und jede hat ihr eigenes Curriculum. Ob das
Band als Ganzes abgedeckt ist, zeigt **IK-Abdeckung im Band** (am Bandkopf der Liste):

- Oben stehen die Curricula des Bands. Mit **Entwürfe einbeziehen** zählen auch die Entwürfe; ein Entwurf, der ein veröffentlichtes Curriculum ersetzen soll, tritt an dessen
  Stelle — so siehst du den Stand nach dem Veröffentlichen.
- Je inhaltsbezogener Kompetenz: **verknüpft**, sobald ein Curriculum sie ganz verknüpft;
  **partiell**, wenn sie nur teilweise vorkommt; sonst **fehlt**. Dahinter steht, welche
  Curricula sie tragen.
- **nur Lücken** blendet die verknüpften aus, **PDF** exportiert die Liste so, wie sie gerade
  angezeigt wird.
- Ein Oberstufen-Curriculum ohne gewähltes Band zählt nicht mit; die Seite nennt es.

### Abdeckung über die Fassung (PK)

Die prozessbezogenen Kompetenzen gelten für alle Klassenstufen einer Fassung — ein einzelnes
Curriculum fördert nie alle. **PK-Abdeckung der Fassung** (am Fassungskopf der Liste) zählt
deshalb über **alle** Curricula des Fachs in dieser Fassung: Je Kompetenz steht, ob sie
gefördert wird, in welchen Curricula und in wie vielen Lernsequenzen. „Entwürfe einbeziehen“,
„nur Lücken“ und PDF funktionieren wie bei der Abdeckung über das Band.

---

## Mit dem Assistenten arbeiten

Der Assistent **Curriculum-Entwurf** baut mit dir ein Curriculum auf oder überarbeitet ein
bestehendes. Du startest ihn im Entwurf mit dem Knopf **Assistent** (Ansicht oder Editor) oder
aus der Assistentenliste — dann fragt er nach Fach und Klassenstufe.

So arbeitet er:

1. **Rahmen klären:** Er fragt nach den Wochenstunden je Stufe und einmal nach Lehrwerk,
   Beschlüssen, Schwerpunkten und einer bisherigen Kapitelfolge. Deine Antworten trägt er in den
   Rahmen ein; „später“ genügt.
2. **Gerüst:** Er schlägt Kapitel und Lernsequenzen mit Stunden vor und nennt darunter, wie
   viele Stunden verplant und wie viele noch frei sind. Die Zahlen rechnet die Plattform, nicht
   die KI.
3. **Kapitel für Kapitel:** Er schlägt je Lernsequenz Einträge mit Kompetenzen vor — nur mit
   Nummern aus dem Bildungsplan der Fassung.

Geschrieben wird erst, wenn du zustimmst. „Ja, aber Kapitel 3 vor 2“ arbeitet er ein und
schreibt dann. Bittest du ihn ausdrücklich, etwas zu löschen („lösch das Kapitel Optik“), ist
das die Zustimmung; er sagt danach, was mit verschwunden ist.

- Er schreibt nur in **Entwürfe**. Ein veröffentlichtes Curriculum liest er und schlägt vor,
  es als Entwurf zu kopieren.
- Jede Speicherung lässt sich zurücknehmen — im Editor mit **Rückgängig** oder im Chat. Stammt
  die letzte Änderung nicht von ihm (aus dem Editor oder von jemand anderem), fragt er vorher
  nach.
- Er kennt nur den Titel des Lehrwerks, nicht seinen Inhalt. Willst du dem Buch folgen, nenn ihm
  Kapitel und Reihenfolge.
- Eine alte Kapitelfolge kannst du in den Chat einfügen. Er übernimmt Reihenfolge und Stunden,
  aber keine alten Kompetenznummern.
- Hat die Schule Leitlinien hinterlegt, fragt er zu Beginn, ob das Curriculum sie
  berücksichtigen soll. Aspekte der Leitperspektiven und der Leitlinien schlägt er dort vor, wo
  sie fachlich passen, und trägt sie in die Hinweise ein.
- **Absprachen mit anderen Fächern** ([oben](#absprachen-mit-anderen-fächern)) kennt er: Arbeitet
  er an einem Kapitel mit Absprachen, nennt er sie — und sagt, wenn die Jahresverlaufspläne eine
  nicht einhalten. Eine Absprache legt er nur an, wenn du ihn darum bittest, etwa „Leg eine
  Absprache mit Mathematik an: Proportionale Zuordnungen vorher“. Er übernimmt auch eine
  Absprache, die eine andere Fachschaft eingetragen hat, als Gegenabsprache, oder macht aus
  Hinweisen wie „in Absprache mit der Fachschaft Chemie …“ Absprachen. Fragst du „Wo wären
  Absprachen sinnvoll?“, nennt er je Kapitel die Bezüge des Bildungsplans zu anderen Fächern und
  wo die andere Fachschaft sie behandelt. Absprachen anderer Fächer und Jahresverlaufspläne
  ändert er nicht.
- Bei großen Vorschlägen dauert eine Antwort manchmal eine Minute.

Veröffentlichen kann er nicht — das geschieht wie immer in der Ansicht.

---

## Begriffe und Fachmethoden

Unter der **Konkretisierung** jedes Eintrags stehen zwei Zeilen: **Begriffe** — die
Fachbegriffe, die die Einheit tragen soll — und **Fachmethoden** — die fachspezifischen
Verfahren, etwa „Titration" oder „Gedichtanalyse". Beides trägst du als Namen ein: tippen,
mit **Enter** übernehmen. Ein Begriff muss dafür noch nicht in der Bibliothek stehen.

### Begriffe

Beim Tippen schlägt die Plattform passende Begriffe aus der Bibliothek deines Fachs und
seiner Bezugsfächer vor. **Enter** übernimmt einen Vorschlag, der genau so heißt, oder den
mit den Pfeiltasten gewählten — sonst den Namen, wie du ihn getippt hast.

Die Farbe zeigt, ob es den Begriff gibt:

| Darstellung | Bedeutung |
|---|---|
| violett, verlinkt | Den Begriff gibt es in der Bibliothek (auch über einen anderen Namen). Aus einem Bezugsfach steht dessen Name dabei. |
| gestrichelt | Platzhalter: Den Begriff gibt es noch nicht. |
| gelb | Es gibt mehrere Begriffe dieses Namens (verschiedene Fassungen). Im Bearbeitungsmodus klickst du darauf und wählst die gemeinte. |

Gespeichert wird der **Name**, keine feste Verknüpfung. Legt die Fachschaft einen
fehlenden Begriff später an, erscheint er von selbst violett — am Curriculum musst du
nichts ändern. Wird ein Begriff in der Bibliothek umbenannt, bleibt der alte Name als
Alias erhalten; das Curriculum findet ihn weiter.

### Fehlende Begriffe anlegen

Zwei Wege, die sich ergänzen:

- **Einzeln:** Am gestrichelten Begriff steht **anlegen** — der Link öffnet das Formular für
  einen neuen Begriff mit dem Namen schon eingetragen. Im Bearbeitungsmodus geht er in einem
  neuen Tab auf, damit nichts Ungespeichertes verloren geht; zurück im Curriculum ist der
  Begriff dann violett. Den Link sehen Mitglieder der Fachschaft des Fachs; alle anderen
  sehen, dass die Fachschaft ihn anlegen kann.
- **Gesammelt:** Über der Tabelle zeigt **„… Begriffe fehlen in der Bibliothek"** aufgeklappt
  jeden fehlenden Begriff mit Anzahl und Kapiteln. Darunter zwei Downloads: die **Liste** zum
  Verteilen in der Fachschaft und **Gerüste (Zip)** — je Begriff eine Datei im Format der
  Fachbegriffe. Definition eintragen, dann das Bündel unter Fachbegriffe einspielen
  ([Fachbegriffe pflegen](fachbegriffe-pflegen.md)). Ein Gerüst ohne Definition weist der
  Import ab, damit kein leerer Begriff in der Sammlung landet.

### Fachmethoden

Fachmethoden sind vorerst nur Namen — es gibt dafür noch keine eigenen Bausteine. Beim
Tippen schlägt die Plattform vor, was in den Curricula deines Fachs schon als Fachmethode
steht, mit der Zahl der Nennungen. So entsteht nicht „Titration", „Titrieren" und
„Säure-Base-Titration" nebeneinander. Ein Name darf auch in beiden Zeilen stehen: als
Begriff (kennen) und als Fachmethode (beherrschen).

### In der Unterrichtsplanung

Ist eine Unterrichtseinheit einem Kapitel zugeordnet, nutzen beide Wege der Planung die
Begriffe dieses Kapitels: Die Leiste **„Kompetenzen und Fachbegriffe"** im Stundenentwurf
schlägt die vor, die die Stunde behandelt, und der Stundenassistent stützt sich darauf,
wenn du ihn nach den Begriffen der Stunde fragst.

Hast du einen **eigenen Stundenassistenten**, kennt er die Anleitung dazu noch nicht: Leg ihn
neu an, damit er den aktuellen schulweiten Prompt übernimmt
([Ein eigener Stundenassistent](unterrichtsplanung.md#ein-eigener-stundenassistent)).

---

## Titel und Jahrgangsband ändern

Beides änderst du im Bearbeitungsmodus direkt im Kopf: den **Titel** durch Klick darauf,
das **Jahrgangsband** im Feld daneben.

Die **Bildungsplan-Fassung** steht dort nur zur Anzeige. Sie lässt sich nicht frei
umstellen, weil an ihr sämtliche Kompetenzverweise hängen — ein Wechsel per Hand würde sie
stillschweigend auf eine andere Fassung zeigen lassen. Dafür gibt es den geprüften Weg im
nächsten Abschnitt.

---

## Auf eine neue Bildungsplan-Fassung wechseln

Erscheint eine überarbeitete Fassung des Bildungsplans, wandert sie **stufenweise** ein —
nicht in allen Jahrgängen gleichzeitig. Dein Curriculum wird deshalb **nicht** automatisch
umgestellt.

In der Ansicht gibt es dafür **„Bildungsplan aktualisieren"**. Du bekommst zuerst eine
**Vorschau**, erst danach passiert etwas. Drei mögliche Ergebnisse:

| Ergebnis | Bedeutung |
|---|---|
| **Keine Aktualisierung nötig** | Das Curriculum liegt schon auf der aktuellen Fassung. |
| **Aktualisieren** | Die neue Fassung gilt für dein ganzes Jahrgangsband — das Curriculum wird umgestellt. |
| **Kopie anlegen** | Die neue Fassung gilt erst für einen Teil des Bandes. Es entsteht eine **Kopie** auf der neuen Fassung — als **Entwurf**; das Original bleibt für die Jahrgänge, die noch nicht gewechselt haben. |

**Was dabei mit den Kompetenzen geschieht:**

- Gleiche Nummer, im Wesentlichen gleicher Text → wird auf die neue Fassung umgehängt.
- Nicht mehr vorhanden oder inhaltlich geändert → bleibt stehen und wird **durchgestrichen
  mit ⚠ markiert**.

Die Markierung ist eine Bitte um Prüfung, kein Fehler: Du musst entscheiden, wodurch die
Kompetenz zu ersetzen ist. Nichts wird stillschweigend gelöscht.

„Bildungsplan aktualisieren“ stellt auf die Fassung um, die **jetzt** gilt. Für eine Fassung,
die erst später gilt, legst du ein neues Curriculum an (siehe [Ein Curriculum
anlegen](#ein-curriculum-anlegen)).

---

## Exportieren

Über **Export** erhältst du das Curriculum als:

- **PDF** — zum Ausdrucken, für Konferenzen und die Fachschaftsakte; Begriffe und
  Fachmethoden stehen als eigene Zeilen unter der Konkretisierung; der Rahmen steht vor dem ersten Kapitel;
  hinter einer Kompetenz stehen die Fächer ihrer Querverweise, etwa „↔ PH, CH“; unter der
  Kapitelüberschrift stehen die eigenen Absprachen mit anderen Fächern
- **DOCX** (Word) oder **ODT** (LibreOffice) — zum Weiterbearbeiten außerhalb der Plattform,
  im Querformat und mit Formeln als bearbeitbare Formeln; Querverweise wie im PDF
- **YAML** — die maschinenlesbare Fassung; Begriffe und Fachmethoden gehen als Namen mit
  und werden in einer anderen Plattform gegen deren Bibliothek abgeglichen; Absprachen mit
  Fach und Kapiteltitel — der Import sucht das Kapitel wieder und warnt, wenn er es nicht
  eindeutig findet

Das YAML ist die einzige Form, die sich wieder einlesen lässt — über **Aus YAML importieren**
(siehe [Aus einer YAML-Datei importieren](#aus-einer-yaml-datei-importieren)), als Entwurf.
Änderungen in Word oder LibreOffice kommen nicht zurück in die Plattform.

---

## Häufige Fragen

**Ich sehe eine Kompetenz durchgestrichen mit ⚠. Habe ich etwas falsch gemacht?**
Nein. Das Curriculum wurde auf eine neue Bildungsplan-Fassung aktualisiert, und diese
Kompetenz gibt es dort nicht mehr oder sie wurde geändert. Ersetze sie, wenn du
Gelegenheit hast.

**Kann ich ein Curriculum kopieren, statt es neu anzulegen?**
Ja: **„Als Entwurf kopieren“** an einem veröffentlichten Curriculum. Die Kopie ersetzt beim
Veröffentlichen das Original. Ein zweites, eigenständiges Curriculum entsteht so nicht —
das gibt es nur beim Fassungswechsel (siehe oben).

**Ich sehe keinen Knopf „Veröffentlichen“.**
Er erscheint nur bei Entwürfen und nur für die, die veröffentlichen dürfen (siehe „Wer darf
was“). An seiner Stelle steht dann, wer es darf.

**Beim Speichern erscheint „diese Verweise zeigen auf Bausteine, die es nicht mehr gibt“.**
Ein Hinweis verweist auf einen Baustein, den ein späterer Import ersetzt hat — etwa einen
ganzen Bildungsplan-Abschnitt. Gespeichert ist trotzdem alles; ersetze den Verweis im Hinweis
durch die gemeinte Kompetenz oder entferne ihn.

**Warum kann ich die Bildungsplan-Fassung nicht einfach umstellen?**
Weil daran alle Kompetenzverweise hängen. Der Weg über „Bildungsplan aktualisieren"
vergleicht jede Kompetenz einzeln und markiert, was nicht passt — das Umstellen von Hand
täte das nicht.

**Ich habe versehentlich etwas gelöscht.**
Noch nicht gespeichert: **Abbrechen** schließt den Editor ohne Änderungen. Schon gespeichert:
**Rückgängig** im Editor (siehe [Rückgängig](#rückgängig)).

**Warum ist ein Begriff gestrichelt, obwohl es ihn gibt?**
Entweder heißt er in der Bibliothek anders — dann lohnt ein Alias am Begriff —, oder er
gehört zu einem Fach, das weder dein Fach noch eines seiner Bezugsfächer ist. Bei gelben
Begriffen gibt es mehrere Fassungen; wähle die gemeinte.

**Mein Oberstufen-Curriculum steht unter „Band nicht zugeordnet“.**
Zu seinen Klassen gibt es im Bildungsplan mehrere Bänder (Basis- und Leistungsfach). Wähle im
Editor unter **Band im Bildungsplan** das richtige und speichere.

**Wer sieht mein Curriculum?**
Alle Lehrkräfte der Schule — auch schon den Entwurf (seit 0.52; bis dahin nur die Fachschaft).
Bearbeiten kann den Entwurf nur die Fachschaft. Schüler:innen sehen ein Curriculum erst, wenn
es veröffentlicht ist. Es ist ein Fachschaftsdokument, kein persönlicher Entwurf.
