/**
 * Farben für Diagramme — aus **Rollen** in `layout.css` (`--diagramm-verbrauch` …).
 *
 * chart.js zeichnet auf eine Leinwand und versteht keine Tailwind-Klassen; es braucht
 * konkrete Farbwerte. Die kommen zur Laufzeit aus CSS-Variablen, statt als `#205ea6` im
 * Komponentencode zu stehen.
 *
 * ⚠️ **Warum Rollen und nicht direkt die semantischen Tokens.** Die erste Fassung las
 * `--color-light-or` usw. unmittelbar. Die Tokens stehen aber in `@theme inline`, und
 * dort gibt Tailwind eine Variable nur aus, wenn ein `var(…)` auf sie verweist —
 * `--color-light-bl` gab es zufällig, `--color-light-or` nicht. Die Soll-Linie fiel auf
 * die schwarze Vorgabefarbe von chart.js zurück (Jan, 02.10.2026). Der Test dazu bestand,
 * weil er die Variablen selbst gesetzt hatte. Die Rollen in `:root`/`.dark` verweisen auf
 * die Tokens; damit gibt es jede verwendete Farbe sicher.
 *
 * **Hell oder dunkel entscheidet das CSS** (`.dark` überschreibt die Rollen), nicht dieses
 * Modul. Schaltet jemand um, muss trotzdem neu gezeichnet werden — `beobachteModus` meldet
 * das.
 */

/**
 * Wert einer Diagrammrolle für den aktuellen Modus.
 * @param {"verbrauch"|"zusage"|"text"|"gitter"|"flaeche"} rolle
 */
export function token(rolle) {
    return getComputedStyle(document.documentElement)
        .getPropertyValue(`--diagramm-${rolle}`)
        .trim();
}

/**
 * Ruft `rueckruf` auf, sobald zwischen hell und dunkel umgeschaltet wird.
 * @returns {() => void}  zum Abmelden (in `onDestroy`)
 */
export function beobachteModus(rueckruf) {
    const beobachter = new MutationObserver(rueckruf);
    beobachter.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["class"],
    });
    return () => beobachter.disconnect();
}
