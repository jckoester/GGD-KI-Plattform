// Mermaid → SVG mit Pele (0.36). Für Export und Bibliothek — im Chat rendert der Browser.
//
// Pele (`github.com/obsidianmd/pele`, MIT) läuft ohne DOM: `render()` ist synchron und misst die
// Schrift mit eigenen Metriken. Gemessen unter 10 ms je Diagramm; Grenzen für Quelle, Ausgabe und
// Kanten setzt Pele selbst. Deshalb im Hauptthread wie MathJax, kein Worker.
//
// Vor dem Rendern dieselbe Reparatur wie im Frontend (Klammern in Beschriftungen), danach feste
// helle Farben statt CSS-Variablen: Word, WeasyPrint und Bildbetrachter werten `var()` nicht aus.
import { render } from 'pele';
import { festeFarben, mermaidReparieren } from './peleHilfen.mjs';

// Breite des Satzspiegels (A4, 2 cm Rand) — wie `SATZSPIEGEL_PX` in `backend/app/render/export.py`.
// Mit `maxWidth` setzt Pele ein zu breites Diagramm neu (eine lange LR-Kette etwa untereinander),
// statt dass es nachträglich auf die Seite geschrumpft wird und der Text unlesbar klein ist.
// Gemessen am Stickstoff-Diagramm aus dem Chat: 2574 × 339 → 615 × 921.
export const SEITENBREITE = 620;

export function renderMermaid(source, idPrefix = 'pele-') {
  const { svg } = render(mermaidReparieren(source), {
    links: false, images: false, idPrefix, maxWidth: SEITENBREITE,
  });
  return festeFarben(svg);
}
