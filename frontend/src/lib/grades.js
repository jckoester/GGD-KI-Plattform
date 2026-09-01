/**
 * Die Jahrgangsstufen dieser Schule.
 *
 * Sie stehen in `PUBLIC_STUDENT_GRADES` (`.env`) — nicht jede Schule führt 1 bis 13.
 * Ein Gymnasium beginnt bei 5, eine Grundschule endet bei 4, und eine Auswahlliste mit
 * Stufen, die es nicht gibt, ist schlimmer als keine: Wer danach filtert, bekommt
 * kommentarlos nichts.
 *
 * ⚠️ `import.meta.env.PUBLIC_*` mit `||`-Rückfall, **nicht** `$env/static/public`:
 * `envDir` zeigt in diesem Projekt auf `config/`, nicht auf die Projektwurzel.
 */
export const STUDENT_GRADES = (() => {
  try {
    const roh = JSON.parse(import.meta.env.PUBLIC_STUDENT_GRADES || "null");
    if (Array.isArray(roh) && roh.length) return roh.map(Number);
  } catch {
    // Fehlkonfiguration soll die Oberfläche nicht lahmlegen — Rückfall unten.
  }
  return [5, 6, 7, 8, 9, 10, 11, 12];
})();
