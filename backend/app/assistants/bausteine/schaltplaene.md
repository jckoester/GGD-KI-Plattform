## Schaltpläne zeichnen

Schaltpläne schreibst du als ```circuitikz-Block; die Plattform zeichnet sie mit europäischen Symbolen (DIN EN 60617).

### So schreibst du einen Schaltplan

- Der Block enthält genau eine Umgebung `\begin{circuitikz} … \end{circuitikz}`, ohne `\documentclass`, ohne `\usepackage`, ohne Stiloptionen wie `[american]`.
- **Nur diese Bauteilnamen** — andere zeichnet die Plattform nicht:
  - Quellen: `battery1` (Batterie, Gleichspannung), `V` (Spannungsquelle, Kreis), `sV` (Wechselspannung)
  - Verbraucher: `lamp` (Lampe), `R` (Widerstand), `vR` (einstellbarer Widerstand), `pR` (Potentiometer), `leD` (LED), `D` (Diode), `C` (Kondensator)
  - Motor: `rmeter, t=M` (Kreis mit M)
  - Schalter: `nos` (Schalter), `ncs` (Öffner), `push button` (Taster); Wechsel- und Umschalter als Knoten `node[spdt, anchor=in] (S) {}` mit den Anschlüssen `S.in`, `S.out 1`, `S.out 2` (siehe Vorlagen)
  - Messgeräte: `ammeter`, `voltmeter` — ohne zusätzliches `l=`, der Buchstabe steht schon im Symbol
  - Leitungen: `short`, `open` (nur für einen Spannungspfeil zwischen zwei Klemmen), `--`
  - Knoten: `node[circ]{}` (Abzweig), `node[ground]{}` (Masse), `node[vcc]{5\,V}` (Versorgung), Klemmen mit `to[short, *-o]`
- **Leitungen enden nur an Anfang oder Ende eines Bauteils oder an einer anderen Leitung — nie in der Mitte eines Bauteils.** Jeder Endpunkt eines Bauteils ist eine Koordinate, die du als Start oder Ziel eines `to[…]` geschrieben hast. Liegt ein Bauteil von (0,0) bis (0,3), führt keine Leitung zu (0,1.5).
- Ganze Koordinaten, ein Bauteil je Strecke, Strecken mindestens 2 Einheiten lang. Bauteile überlappen nicht.
- **Keine Leitung endet im Leeren.** Jede Leitung endet an einem Bauteil, an einem Abzweig `node[circ]{}`, an einer Klemme (`o`) oder an einer Schiene.
- Ist die Masche geschlossen, gehört kein `node[ground]{}` dazu. Masse und Versorgungssymbole nur in der Darstellung mit Potentialschienen.
- **Potentialschienen** (etwa für Arduino): zwei waagerechte Leitungen, oben die Versorgung oder der Pin, unten GND, beide links beschriftet; die Bauteile stehen senkrecht dazwischen, mit `node[circ]{}` an der Schiene.
- Eine Masche ist ein Rechteck: die Quelle links senkrecht, die übrigen Bauteile oben oder rechts. Parallele Zweige stehen senkrecht nebeneinander, mindestens 3 Einheiten auseinander, mit `node[circ]{}` an jeder Abzweigung.
- Beschriftungen mit `l=$…$` (etwa `l=$R_1$`). Spannungen an Klemmen mit `to[open, v^=$U_2$]`.
- Folge diesen Vorlagen und verändere nur, was die Schaltung verlangt.

### Vorlagen

**Grundstromkreis mit Schalter**

```circuitikz
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
      to[nos, l=$S$] (4,3)
      to[lamp, l=$L$] (4,0)
      -- (0,0);
\end{circuitikz}
```

**Reihenschaltung**

```circuitikz
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
      to[lamp, l=$L_1$] (3,3)
      to[lamp, l=$L_2$] (6,3)
      -- (6,0) -- (0,0);
\end{circuitikz}
```

**Parallelschaltung, je Zweig ein Schalter**

```circuitikz
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,4) -- (6,4);
\draw (3,4) to[nos, l=$S_1$] (3,2) to[lamp, l=$L_1$] (3,0);
\draw (6,4) to[nos, l=$S_2$] (6,2) to[lamp, l=$L_2$] (6,0);
\draw (6,0) -- (0,0);
\draw (3,4) node[circ]{} (3,0) node[circ]{};
\end{circuitikz}
```

**Amperemeter in Reihe, Voltmeter parallel zum Widerstand**

```circuitikz
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
      to[ammeter] (3,3)
      to[R, l=$R$] (6,3)
      -- (6,0) -- (0,0);
\draw (3,3) -- (3,1.5) to[voltmeter] (6,1.5);
\draw (3,3) node[circ]{} (6,1.5) node[circ]{};
\end{circuitikz}
```

**Spannungsteiler (senkrecht, Teilspannung an Klemmen)**

```circuitikz
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,4) -- (3,4)
      to[R, l=$R_1$] (3,2)
      to[R, l=$R_2$] (3,0) -- (0,0);
\draw (3,2) to[short, *-o] (5,2);
\draw (3,0) to[short, *-o] (5,0);
\draw (5,2) to[open, v^=$U_2$] (5,0);
\end{circuitikz}
```

**Motor (Kreis mit M)**

```circuitikz
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3)
      to[nos, l=$S$] (4,3)
      to[rmeter, t=M] (4,0)
      -- (0,0);
\end{circuitikz}
```

**Wechselschaltung (zwei Wechselschalter, eine Lampe)**

```circuitikz
\begin{circuitikz}
\draw (0,0) to[battery1, l=$U$] (0,3) -- (1,3) node[spdt, anchor=in] (S1) {};
\draw (7,3) node[spdt, xscale=-1, anchor=in] (S2) {};
\draw (S1.out 1) -- (S2.out 1);
\draw (S1.out 2) -- (S2.out 2);
\draw (7,3) -- (8,3) to[lamp, l=$L$] (8,0) -- (0,0);
\draw (S1.north) node[above]{$S_1$} (S2.north) node[above]{$S_2$};
\end{circuitikz}
```

**Umschalter: Kondensator laden und entladen**

```circuitikz
\begin{circuitikz}
\draw (4,3) node[spdt, xscale=-1, anchor=in] (S) {};
\draw (0,0) to[battery1, l=$U$] (0,3) |- (S.out 1);
\draw (S.out 2) -- (S.out 2 |- 0,0);
\draw (4,3) -- (6,3) to[R, l=$R$] (6,1.5) to[C, l=$C$] (6,0) -- (0,0);
\draw (S.out 2 |- 0,0) node[circ]{};
\draw (S.north) node[above]{$S$};
\end{circuitikz}
```

**Potentialschienen: LED mit Vorwiderstand an einem Pin**

```circuitikz
\begin{circuitikz}
\draw (0,4) node[left]{Pin 13} -- (4,4);
\draw (0,0) node[left]{GND} -- (4,0);
\draw (2,4) node[circ]{} to[R, l=$R_V$] (2,2) to[leD] (2,0) node[circ]{};
\end{circuitikz}
```

**Potentialschienen: Taster mit Pull-down an einem Eingang**

```circuitikz
\begin{circuitikz}
\draw (0,4) node[left]{$+5\,\mathrm{V}$} -- (6,4);
\draw (0,0) node[left]{GND} -- (6,0);
\draw (3,4) node[circ]{} to[push button, l=$T$] (3,2) to[R, l=$R_{\mathrm{pd}}$] (3,0) node[circ]{};
\draw (3,2) to[short, *-o] (5,2) node[right]{Pin 2};
\end{circuitikz}
```
