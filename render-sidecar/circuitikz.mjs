// CircuiTikZ-Quelle des Modells → vollständiges TeX-Dokument für node-tikzjax (0.37).
//
// Abhängigkeitsfrei, damit `test/circuitikz.test.mjs` sie ohne TeX-Motor prüfen kann.
//
// Gemessen (Plaene/Messungen-Schaltplaene, Lauf 1): Von 67 Schaltplänen aus dem freien Chat ließen
// sich 17 zeichnen. `chat-komplex` schrieb in 30 von 34 Fällen nur die `\draw`-Zeilen ohne
// `circuitikz`-Umgebung; `chat-standard` meist `[american]`. Deshalb, in dieser Reihenfolge:
//
// 1. Präambel des Modells entfernen (`\documentclass`, `\usepackage`, `\begin{document}` …) — die
//    setzt dieses Modul selbst; doppelt bricht das Rendern ab.
// 2. Amerikanische Stiloptionen streichen (`[american]`, `american voltages` …, `\ctikzset{american}`).
//    Im Schulkontext gelten DIN/IEC-Symbole (Plan F1) — ein Modell, das `american` schreibt, meint es nicht.
// 3. Fehlt eine Umgebung, `\begin{circuitikz}…\end{circuitikz}` darum setzen. Eine `tikzpicture` bleibt:
//    CircuiTikZ-Bauteile funktionieren auch darin.
// 4. Paket mit `european` laden: Widerstand als Rechteck, Lampe als Kreis mit Kreuz. Dazu `amsmath`:
//    Modelle schreiben Einheiten als `$9\,\text{V}$`, und `\text` gibt es nur mit amsmath (Lauf 3).
// 5. Schalter als Schulsymbol: `switch`/`spst`/`closing switch` zeichnet CircuiTikZ als „schließenden
//    Schalter“ mit Bogenpfeil (ein Schaltvorgang), nicht als einfachen Schalter. Der heißt `nos`; der
//    Öffner (`opening switch`/`ospst`) wird `ncs`. Eine Stilfrage wie `european`, kein Raten (Jan, 07.11.2026).
//
// 6. Zeichen, die der TeX-Motor (CircuiTikZ 1.0, 2020) nicht kennt, ersetzen: schmale Leerzeichen
//    (U+202F, U+2009 — `chat-standard` schreibt „Pin 13“ mit U+202F) durch normale, Ω/µ/°/× durch
//    `\ensuremath{…}`, das in und außerhalb von Formeln gilt. Umlaute und Gedankenstrich gehen (Lauf 3).
//
// Erfundene Bauteilnamen (`closed switch`) bleiben ein Fehler; sie umzubenennen hieße raten (Plan F2).

const PRAEAMBEL = /^\s*\\(documentclass|usepackage|usetikzlibrary)\b[^\n]*$|^\s*\\(begin|end)\{document\}\s*$/gm;
const AMERIKANISCH = /^(american|us)(\s+(voltages?|currents?|resistors?|inductors?|ports?|gfsurgearrester))?$/i;

function ohneAmerikanisch(optionen) {
  return optionen.split(',').map((o) => o.trim()).filter((o) => o && !AMERIKANISCH.test(o)).join(', ');
}

// Bauteilname am Anfang der Optionen von `to[…]`, gefolgt von `,` oder `]`.
const SCHLIESSER = /(to\s*\[\s*)(closing switch|cspst|spst|switch)(?=\s*[,\]])/g;
const OEFFNER = /(to\s*\[\s*)(opening switch|ospst)(?=\s*[,\]])/g;

const ZEICHEN = [
  [/[\u2007\u2009\u202f]/g, ' '],
  [/Ω/g, '\\ensuremath{\\Omega}'],
  [/[µμ]/g, '\\ensuremath{\\mu}'],
  [/°/g, '\\ensuremath{^\\circ}'],
  [/×/g, '\\ensuremath{\\times}'],
];

/** Die Quelle aufbereitet: ohne Präambel, ohne amerikanische Stiloptionen, mit Umgebung. */
export function circuitikzAufbereiten(source) {
  let s = ZEICHEN.reduce((t, [muster, ersatz]) => t.replace(muster, ersatz), source).replace(PRAEAMBEL, '');
  s = s.replace(/\\begin\{(circuitikz|tikzpicture)\}\s*\[([^\]]*)\]/g, (_, umgebung, optionen) => {
    const rest = ohneAmerikanisch(optionen);
    return rest ? `\\begin{${umgebung}}[${rest}]` : `\\begin{${umgebung}}`;
  });
  s = s.replace(/\\ctikzset\{\s*(american|US)[^}]*\}/gi, '');
  s = s.replace(SCHLIESSER, '$1nos').replace(OEFFNER, '$1ncs');
  if (!/\\begin\{(circuitikz|tikzpicture)\}/.test(s)) {
    s = `\\begin{circuitikz}\n${s.trim()}\n\\end{circuitikz}`;
  }
  return s.trim();
}

/** Vollständiges TeX-Dokument mit europäischen Symbolen. */
export function wrapCircuit(source) {
  return `\\usepackage{amsmath}\n\\usepackage[european]{circuitikz}\n\\begin{document}\n${circuitikzAufbereiten(source)}\n\\end{document}`;
}
