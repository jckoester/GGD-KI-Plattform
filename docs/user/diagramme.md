# Diagramme, Schaltpläne, Funktionsgraphen & Strukturformeln

Assistenten können in ihren Antworten **Bilder aus Beschreibungen** erzeugen — du musst dafür
nichts installieren oder zeichnen können, sondern nur danach fragen.

## Was geht?

- **Diagramme** (Flussdiagramme, Abläufe, Strukturen) — z. B. „Zeichne ein Flussdiagramm für …".
- **Elektrische Schaltpläne** — z. B. „Zeichne den Schaltplan einer Reihenschaltung mit zwei
  Widerständen und einer Lampe." Mehr dazu [unten](#schaltpläne).
- **Funktionsgraphen** — z. B. „Zeichne den Graphen von f(x) = x² − 2 im Bereich −4 bis 4."
  Die Achsen gehen durch den Ursprung und tragen Pfeile; haben x und y ähnliche Spannen, gilt auf
  beiden Achsen dieselbe Einheit. Eine Polstelle wie bei 1/x sprengt den Bildausschnitt nicht.
- **Strukturformeln** (Chemie) — z. B. „Zeichne die Strukturformel von Ethanol" oder „Zeige die
  Grenzformeln des Phenolat-Ions". Mehr dazu [unten](#strukturformeln).

Der Assistent beschreibt die Grafik in einem Code-Block, der bei uns automatisch als Bild
dargestellt wird. Fährst du mit der Maus über die Grafik, erscheint oben rechts dieselbe Leiste
wie an Bildern und Texten:

- **„Speichern"** — legt die Grafik dauerhaft in der [Werkstatt](werkstatt.md) ab; sonst
  verschwindet sie mit dem Chat.
- **„Herunterladen"** — die Grafik als SVG-Datei. Sie ist **immer hell**, auch wenn du den
  Dunkelmodus nutzt, damit sie auf weißem Papier lesbar bleibt.
- **„Code kopieren"** — der Quelltext der Grafik, etwa um sie in einem Dokument der
  Werkstatt weiterzuverwenden.
- **„GeoGebra"** — nur bei Funktionsgraphen: eine `.ggb`-Datei zum Weiterbearbeiten.

Ist eine Grafik zu breit für den Chat, wird sie verkleinert und bekommt unten rechts Knöpfe zum
**Vergrößern** und Verkleinern; vergrößert verschiebst du sie mit der Maus. Dasselbe geht in der
[Werkstatt](werkstatt.md) in der Ansicht des gespeicherten Diagramms.

## Schaltpläne

Schaltpläne erscheinen mit den **Symbolen aus dem Unterricht** (DIN/IEC): der Widerstand als
Rechteck, der Schalter als einfacher Hebel.

Am besten gelingen sie mit dem Assistenten **„Schaltpläne zeichnen“** (Physik, ab Klasse 8). Fragst
du im Chat nach einem Schaltplan, schlägt der Chat ihn dir vor. Er kennt bewährte Vorlagen und
zeichnet deshalb sauberer als der Chat ohne Assistenten:

- Grundstromkreis, Reihen- und Parallelschaltung, gemischte Schaltungen;
- Amperemeter und Voltmeter, LED mit Vorwiderstand, Motor, Potentiometer, Kondensator;
- Wechselschaltung und Umschalter;
- Spannungsteiler;
- **Potentialschienen** wie bei Arduino-Schaltungen: 5 V oben, GND unten.

Auf Wunsch zeichnet er mehrere Pläne zum Vergleichen, etwa für ein Arbeitsblatt.

**Ist der Schaltplan deine Aufgabe**, zum Beispiel eine Hausaufgabe, zeichnet der Assistent ihn
dir nicht vor. Er hilft dir Schritt für Schritt zu deinem eigenen Plan, und den fertigen
bekommst du zum Vergleich, wenn du deinen beschrieben hast. Zum Verstehen oder Wiederholen
zeichnet er sofort.

Ob der Assistent an deiner Schule für Schüler:innen freigeschaltet ist, entscheidet die Schule.

## Strukturformeln

Fragst du nach einer Strukturformel, zeichnet der Chat sie als Bild:

- **Valenzstrichformel** ist die Vorgabe: alle Atome, auch die Wasserstoffatome, und die
  **freien Elektronenpaare als Striche**. Die Elektronenpaare berechnet die Plattform aus der
  Formel selbst — sie fehlen also nicht und stehen nicht doppelt.
- **Skelettformel** bekommst du, wenn du ausdrücklich danach fragst („Zeichne die Skelettformel
  von Ibuprofen"). Freie Elektronenpaare stehen dann nur an Atomen, die nicht Kohlenstoff sind,
  und an geladenen Atomen.
- **Mehrere Formeln in einer Reihe:** Grenzformeln mit Mesomeriepfeil (↔), Reaktionen mit
  Reaktionspfeil (→) oder Gleichgewichtspfeil (⇌), Moleküle mit Namen darunter.
- **Elektronenpfeile** für Reaktionsmechanismen kann der Chat nicht zeichnen. Der Assistent
  beschreibt sie dann in Worten.

Hat sich der Assistent bei einem Molekül vertan (etwa ein Kohlenstoff mit fünf Bindungen),
steht an dessen Stelle ein **gestrichelter Kasten „nicht darstellbar"** mit der Formel; die
übrigen Moleküle der Reihe bleiben sichtbar. Weise den Assistenten auf den Fehler hin.

Im Dunkelmodus stehen Strukturformeln auf einer hellen Karte, weil die Farben der Atome
(Sauerstoff rot, Stickstoff blau) etwas bedeuten.

## Gut zu wissen

- **Formeln** (z. B. `$\frac{U}{R}$`) werden als richtige mathematische Schrift dargestellt.
  Lässt sich eine Formel nicht darstellen, steht dort **„Formel nicht darstellbar"**; ein Klick
  darauf klappt den Quelltext auf.
- Klappt eine Grafik mal nicht (z. B. ein sehr ungewöhnlicher Schaltplan), erscheint statt des
  Bildes ein kurzer Hinweis mit der Beschreibung. Bitte den Assistenten dann, es anders zu
  formulieren.
- **Für Lehrkräfte:** Wenn du gezielt einen Funktionsgraphen möchtest, hilft eine klare Angabe
  von **Funktion(en) und Wertebereich**. Der Assistent kennt das passende ```plot-Format
  (Funktionen als `f(x) = …`, Multiplikation immer mit `*`, Potenzen mit `^`); du kannst es aber
  auch einfach in Worten beschreiben.
