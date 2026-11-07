// Tests der Aufbereitung (0.37): `node --test render-sidecar/test/`
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { circuitikzAufbereiten, wrapCircuit } from '../circuitikz.mjs';

test('fehlende Umgebung wird ergänzt (chat-komplex, 30 von 34)', () => {
  const s = circuitikzAufbereiten('\\draw (0,0) to[battery1] (0,3);');
  assert.match(s, /^\\begin\{circuitikz\}\n\\draw/);
  assert.match(s, /\\end\{circuitikz\}$/);
});

test('vorhandene Umgebung bleibt, auch eine tikzpicture', () => {
  const c = '\\begin{circuitikz}\n\\draw (0,0) to[R] (2,0);\n\\end{circuitikz}';
  assert.equal(circuitikzAufbereiten(c), c);
  const t = '\\begin{tikzpicture}\n\\draw (0,0) to[R] (2,0);\n\\end{tikzpicture}';
  assert.equal(circuitikzAufbereiten(t), t);
});

test('amerikanische Optionen fallen weg, andere bleiben', () => {
  assert.equal(circuitikzAufbereiten('\\begin{circuitikz}[american]\nX\n\\end{circuitikz}'),
    '\\begin{circuitikz}\nX\n\\end{circuitikz}');
  assert.equal(circuitikzAufbereiten('\\begin{circuitikz}[american voltages, scale=0.8]\nX\n\\end{circuitikz}'),
    '\\begin{circuitikz}[scale=0.8]\nX\n\\end{circuitikz}');
  assert.doesNotMatch(circuitikzAufbereiten('\\ctikzset{american}\n\\draw (0,0);'), /american/);
});

test('Präambel des Modells fällt weg', () => {
  const s = circuitikzAufbereiten(
    '\\documentclass{standalone}\n\\usepackage[american]{circuitikz}\n\\begin{document}\n'
    + '\\begin{circuitikz}\n\\draw (0,0) to[R] (2,0);\n\\end{circuitikz}\n\\end{document}');
  assert.doesNotMatch(s, /documentclass|usepackage|\{document\}/);
  assert.match(s, /^\\begin\{circuitikz\}/);
});

test('das Dokument lädt CircuiTikZ europäisch', () => {
  const d = wrapCircuit('\\draw (0,0) to[R] (2,0);');
  assert.match(d, /^\\usepackage\[european\]\{circuitikz\}\n\\begin\{document\}\n\\begin\{circuitikz\}/);
  assert.match(d, /\\end\{circuitikz\}\n\\end\{document\}$/);
});
