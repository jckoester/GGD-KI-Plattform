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
// 4. Paket mit `european` laden: Widerstand als Rechteck, Lampe als Kreis mit Kreuz.
//
// Erfundene Bauteilnamen (`closed switch`) bleiben ein Fehler; sie umzubenennen hieße raten (Plan F2).

const PRAEAMBEL = /^\s*\\(documentclass|usepackage|usetikzlibrary)\b[^\n]*$|^\s*\\(begin|end)\{document\}\s*$/gm;
const AMERIKANISCH = /^(american|us)(\s+(voltages?|currents?|resistors?|inductors?|ports?|gfsurgearrester))?$/i;

function ohneAmerikanisch(optionen) {
  return optionen.split(',').map((o) => o.trim()).filter((o) => o && !AMERIKANISCH.test(o)).join(', ');
}

/** Die Quelle aufbereitet: ohne Präambel, ohne amerikanische Stiloptionen, mit Umgebung. */
export function circuitikzAufbereiten(source) {
  let s = source.replace(PRAEAMBEL, '');
  s = s.replace(/\\begin\{(circuitikz|tikzpicture)\}\s*\[([^\]]*)\]/g, (_, umgebung, optionen) => {
    const rest = ohneAmerikanisch(optionen);
    return rest ? `\\begin{${umgebung}}[${rest}]` : `\\begin{${umgebung}}`;
  });
  s = s.replace(/\\ctikzset\{\s*(american|US)[^}]*\}/gi, '');
  if (!/\\begin\{(circuitikz|tikzpicture)\}/.test(s)) {
    s = `\\begin{circuitikz}\n${s.trim()}\n\\end{circuitikz}`;
  }
  return s.trim();
}

/** Vollständiges TeX-Dokument mit europäischen Symbolen. */
export function wrapCircuit(source) {
  return `\\usepackage[european]{circuitikz}\n\\begin{document}\n${circuitikzAufbereiten(source)}\n\\end{document}`;
}
