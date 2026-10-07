/**
 * Die Regeln der Importvorschau (Paket 10, AP4) — ohne Svelte, damit prüfbar.
 *
 * Der Bericht des Endpunkts ist eine Liste von Zeilen plus Summen. Was daraus eine
 * Vorschau macht, sind Entscheidungen: In welcher Reihenfolge stehen die Gruppen? Welche
 * Zeile darf überschrieben werden? Wann lohnt der Knopf „einspielen" überhaupt? Diese
 * Entscheidungen stehen hier und nicht in der Komponente — das Projekt prüft Regeln im
 * Modul (vgl. `abbildungen.js`, `uebernahme.js`).
 */

/**
 * Sammlungen, in die ein Bündel eingespielt werden kann.
 *
 * ⚠️ **Dieselbe Liste steht im Backend** als `TYPEN` in `fachbegriffe_import.py` — sie
 * entscheidet dort, welche `knotentyp:`-Werte der Leser annimmt. Liefe sie auseinander,
 * böte die Oberfläche einen Knopf an, der nichts einspielt, oder ließe eine Sammlung
 * ohne Knopf. `backend/tests/unit/test_taxonomy_check.py` hält beide zusammen.
 */
export const IMPORTIERBARE_TYPEN = ["begriff", "stoffsteckbrief"];

/**
 * Stehen „Aus Dateien" und „Als Zip" an dieser Stelle zur Verfügung?
 *
 * Zwei Bedingungen, und beide sind leicht zu vergessen:
 *
 * 1. **Ein Fach muss feststehen.** Die Werkzeuge gehören einer Fachschaft; ohne Fach
 *    wüsste weder die Oberfläche, wohin, noch das Backend, wessen Rechte zu prüfen
 *    sind. ⚠️ `KnowledgeNodeList` steht auch unter `/knowledge` ganz ohne Fach — dort
 *    darf der Knopf nicht auftauchen, und das sieht man der Komponente nicht an.
 * 2. **Lehrkraft.** Die Sammlungen stehen auch Schüler:innen offen; das Einspielen
 *    nicht. (Admin ist eine Erweiterung der Lehrkraft-Rolle, siehe CLAUDE.md — deshalb
 *    genügt die Prüfung auf `teacher`.)
 *
 * Das Backend prüft beides noch einmal und schärfer (Mitgliedschaft in der
 * Fachschaft); hier geht es nur darum, keinen Knopf zu zeigen, der mit 403 antwortet.
 */
export function zeigeDateiwerkzeuge(fach, rollen) {
  return Boolean(fach) && (rollen ?? []).includes("teacher");
}

/**
 * Die fünf Zustände, in der Reihenfolge, in der sie jemanden interessieren.
 *
 * ⚠️ **Handänderungen zuerst.** Sie sind das Einzige, wozu die Vorschau eine Frage
 * stellt; alles andere ist Bericht. Stünden sie hinter dreißig „unverändert"-Zeilen,
 * würde die Frage überlesen — und der nächste Lauf überschriebe entweder zu viel oder
 * ließe eine Überarbeitung liegen.
 */
export const ZUSTAENDE = [
  {
    zustand: "uebersprungen",
    label: "In der Oberfläche bearbeitet",
    erklaerung:
      "Seit dem letzten Einspielen hat jemand an diesen Einträgen gearbeitet. " +
      "Sie bleiben, wie sie sind — außer du entscheidest hier anders.",
  },
  {
    zustand: "uebergangen",
    label: "Nicht eingespielt",
    erklaerung: "Diese Dateien konnten nicht zugeordnet werden; der Grund steht unten.",
  },
  { zustand: "neu", label: "Neu", erklaerung: "Kommt hinzu." },
  { zustand: "aktualisiert", label: "Wird aktualisiert", erklaerung: "Die Datei gewinnt." },
  {
    zustand: "unveraendert",
    label: "Unverändert",
    erklaerung: "Steht schon genau so im Speicher.",
  },
];

/** Zeilen nach Zustand, leere Gruppen fallen weg. */
export function gruppiert(bericht) {
  const zeilen = bericht?.dateien ?? [];
  return ZUSTAENDE.map((gruppe) => ({
    ...gruppe,
    zeilen: zeilen.filter((z) => z.zustand === gruppe.zustand),
  })).filter((gruppe) => gruppe.zeilen.length > 0);
}

/**
 * Dateien, die einen anderen Prüfstatus tragen als „geprüft".
 *
 * Import **ist** Freigabe — was eingespielt wird, sehen alle, die das Fach lesen dürfen.
 * Deshalb fragt die Vorschau nach, verhindert aber nichts: Ob ein Entwurf reif ist,
 * weiß die Fachschaft, nicht die Software.
 */
export function entwuerfe(bericht) {
  return (bericht?.dateien ?? []).filter((z) => z.entwurf);
}

/** „2 neu · 1 aktualisiert · 33 unverändert" — die Zeile über der Tabelle. */
export function zusammenfassung(bericht) {
  if (!bericht) return "";
  const teile = [
    [bericht.neu, "neu"],
    [bericht.aktualisiert, "aktualisiert"],
    [bericht.unveraendert, "unverändert"],
    [bericht.uebersprungen?.length ?? 0, "behalten"],
  ].filter(([n]) => n > 0);
  if (teile.length === 0) return "Nichts zu tun.";
  return teile.map(([n, wort]) => `${n} ${wort}`).join(" · ");
}

/**
 * Würde ein echter Lauf etwas ändern?
 *
 * ⚠️ Gerechnet wird mit der **aktuellen Auswahl**, nicht mit dem Bericht allein: Ein
 * Probelauf ohne Auswahl meldet „0 aktualisiert" für einen handveränderten Knoten —
 * wer ihn gerade angehakt hat, würde sehr wohl etwas ändern. Ohne das wäre der Knopf
 * genau dann aus, wenn er gebraucht wird.
 */
export function lohntSich(bericht, auswahl = []) {
  if (!bericht) return false;
  return bericht.neu > 0 || bericht.aktualisiert > 0 || auswahl.length > 0;
}

/** Was nach dem Lauf im Speicher gelandet ist — mit Knoten-ID, also verlinkbar. */
export function eingespielt(bericht) {
  return (bericht?.dateien ?? []).filter(
    (z) => z.node_id && (z.zustand === "neu" || z.zustand === "aktualisiert"),
  );
}

/**
 * Müssen Vektoren neu berechnet werden?
 *
 * Neue und geänderte Knoten sind sofort über Namen und Aliase auffindbar, über die
 * **Bedeutung** erst, wenn ihr Vektor da ist. Seit 0.14 rechnet der Endpunkt ihn gleich
 * nach dem Import im Hintergrund (vorher erst nachts) — ein paar Augenblicke bleiben,
 * und scheitert es, holt der nächtliche Lauf es nach. Das gehört in die Rückmeldung.
 */
export function brauchtEinbettung(bericht) {
  return (bericht?.neu ?? 0) > 0 || (bericht?.neu_einzubetten ?? 0) > 0;
}
