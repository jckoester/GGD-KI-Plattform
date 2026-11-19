/**
 * Form der Chips über dem Chat-Eingabefeld (0.49, H5): **D-Form** — links fast eckig mit
 * Akzentrand, rechts rund; getönter Grund. Gilt für alle Chips über dem Eingabefeld:
 * Assistent und Fach (Chat-Seite), Bausteine (`ContextChips`), Produkte aus der Werkstatt
 * (`ProduktChips`, Akzent wie „Material“) und hochgeladene Dateien (`AttachmentChip`). Eine beidseitig runde Pille mit Akzentrand links sah nicht aus
 * (Jan, 19.11.2026).
 *
 * Die Fachfarbe kommt als Hexwert aus `subjects.yaml` und lässt sich deshalb nicht als
 * Tailwind-Klasse schreiben; sie geht per `style` an den Chip. Ohne (gültige) Fachfarbe gilt
 * der blaue Akzent der Kontext-Chips.
 */

/** Grundform; der Akzent kommt dazu (`AKZENT_BLAU` oder `fachAkzentStil`). Schrift `tx`, nicht
 *  `tx-2`: auf getöntem Grund war das Grau zu schwach (Jan, 19.11.2026). Kein eigener Grund:
 *  `bg-light-bg-2` neben der Tönung des Akzents wären zwei Hintergründe in einer Klassenliste. */
export const CHIP_FORM =
    "inline-flex items-center gap-1.5 pl-1.5 pr-2 py-1 rounded-l-sm rounded-r-full text-xs border border-l-4 " +
    "text-light-tx dark:text-dark-tx";

/** Icon-Größe in allen Chips (px), damit Kontext-, Fach- und Assistent-Chip gleich hoch sind. */
export const CHIP_ICON = 14;

/**
 * Akzente als Tailwind-Klassen: Rand rundum zart, links voll, Grund getönt. Die Klassen müssen
 * wörtlich im Quelltext stehen (Tailwind sucht sie dort). Kürzel wie `CATEGORY_COLORS`.
 */
export const CHIP_AKZENT = {
    bl: "border-light-bl/30 dark:border-dark-bl/30 border-l-light-bl dark:border-l-dark-bl bg-light-bl/10 dark:bg-dark-bl/10",
    gr: "border-light-gr/30 dark:border-dark-gr/30 border-l-light-gr dark:border-l-dark-gr bg-light-gr/10 dark:bg-dark-gr/10",
    or: "border-light-or/30 dark:border-dark-or/30 border-l-light-or dark:border-l-dark-or bg-light-or/10 dark:bg-dark-or/10",
    pu: "border-light-pu/30 dark:border-dark-pu/30 border-l-light-pu dark:border-l-dark-pu bg-light-pu/10 dark:bg-dark-pu/10",
    // Fehler (Anhang nicht hochgeladen)
    re: "border-light-re/30 dark:border-dark-re/30 border-l-light-re dark:border-l-dark-re bg-light-re/10 dark:bg-dark-re/10",
    // Ohne Bedeutungsfarbe (hochgeladene Dateien)
    neutral: "border-light-ui-3 dark:border-dark-ui-3 border-l-light-tx-2 dark:border-l-dark-tx-2 bg-light-bg-2 dark:bg-dark-bg-2",
};

/** Akzent ohne Fachfarbe. */
export const AKZENT_BLAU = CHIP_AKZENT.bl;

const HEX = /^#[0-9a-fA-F]{6}$/;

/**
 * `style` für den Akzent in der Fachfarbe: Rand links voll, rundum zu 25 %, Grund zu 10 %.
 * Ohne eigene Randfarbe nähme Tailwind 4 die Schriftfarbe — ein dunkler Rahmen (Jan, 19.11.2026).
 * Leer, wenn die Farbe fehlt oder kein sechsstelliger Hexwert ist — dann gilt `AKZENT_BLAU`.
 */
export function fachAkzentStil(farbe) {
    if (typeof farbe !== "string" || !HEX.test(farbe)) return "";
    return `border-color: ${farbe}40; border-left-color: ${farbe}; background-color: ${farbe}1a`;
}

/** Klassen für den Chip: Grundform plus blauer Akzent, wenn keine Fachfarbe greift. */
export function chipKlasse(farbe) {
    return fachAkzentStil(farbe) ? CHIP_FORM : `${CHIP_FORM} ${AKZENT_BLAU}`;
}

/**
 * Höhe von zwei Chip-Zeilen samt Abstand (`NachrichtenChips` eingeklappt, `max-h-[3.75rem]`):
 * Chip 26 px (py-1, text-xs, Rand), Abstand 6 px → 58 px; 60 lässt Luft für Rundung.
 */
export const ZWEI_ZEILEN_PX = 60;

/**
 * Wie viele Chips liegen unterhalb des sichtbaren Rahmens? Gezählt werden die direkten
 * Kinder, deren Oberkante nicht mehr hineinpasst (`feld` ist `relative`, also ihr
 * `offsetParent`).
 */
export function versteckteChips(feld) {
    if (!feld) return 0;
    const hoehe = feld.clientHeight;
    return [...feld.children].filter((k) => k.offsetTop >= hoehe).length;
}
