/**
 * Klassen für kleine Etiketten an Assistentenkarten (0.27, Plan Schritt 9.2).
 *
 * ⚠️ Bis 0.27 hatten die Etiketten Schrift in `tx-3` auf `ui-2` (hell 1,4 : 1, dunkel 1,7 : 1)
 * bzw. `tx-2` auf `ui-3` (dunkel 2,9 : 1) — im dunklen Modus kaum lesbar (Jan, 01.11.2026).
 * Gefordert sind 4,5 : 1 (WCAG AA). Diese Kombination erreicht hell 5,1 : 1, dunkel 7,9 : 1
 * (gemessen an den fexoki-Werten in `layout.css`). Alle neutralen Etiketten nehmen sie.
 */
export const BADGE =
  "text-xs px-1.5 py-0.5 rounded-full bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx-2 dark:text-dark-tx";
