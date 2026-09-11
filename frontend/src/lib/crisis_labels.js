/**
 * Beschriftungen für Krisen-Flags — Schweregrad und Kategorie.
 *
 * Lag bis 10.09.2026 dreifach kopiert in `/flags`, `/review` und
 * `/access-requests/[id]`, und war schon auseinandergelaufen: Die dritte Kopie
 * führte `SEVERITY` als reine Zeichenkette, die beiden anderen als Objekt mit
 * Klassen. Der Kontrastfehler in den Chips steckte deshalb an zwei Stellen und
 * musste zweimal behoben werden.
 *
 * Die Farbklassen stehen hier mit, nicht nur die Wörter: Ein Schweregrad ohne
 * seine Farbe ist keine vollständige Angabe, und getrennte Tabellen laufen
 * wieder auseinander.
 */

/** Fläche + Rand tragen die Farbe, die Schrift bleibt die gewohnte.
 *
 * Nicht `bg-*-re-2` mit `text-*-re` — das sind zwei Nachbarstufen derselben
 * Palettenfamilie (1,45–1,48:1). Siehe den Hinweis bei den `-bg`-Token in
 * `routes/layout.css`. */
export const SEVERITY = {
    alert: {
        label: "Alarm",
        cls: "bg-light-re-bg dark:bg-dark-re-bg border border-light-re dark:border-dark-re",
    },
    warning: {
        label: "Warnung",
        cls: "bg-light-or-bg dark:bg-dark-or-bg border border-light-or dark:border-dark-or",
    },
    info: {
        label: "Hinweis",
        cls: "bg-light-bl-bg dark:bg-dark-bl-bg border border-light-bl dark:border-dark-bl",
    },
};

/** Neutrale Ausweichklasse für einen Schweregrad, den diese Fassung nicht kennt. */
export const SEVERITY_FALLBACK =
    "bg-light-ui-2 dark:bg-dark-ui-2 border border-light-ui-3 dark:border-dark-ui-3";

export const CATEGORY = {
    suizidalitaet: "Suizidalität",
    selbstverletzung: "Selbstverletzung",
    haeusliche_gewalt: "Häusliche Gewalt",
    essverhalten: "Essverhalten",
    mobbing: "Mobbing",
};

/** Beschriftung eines Schweregrads; unbekannte Werte kommen unverändert zurück,
 *  damit ein neuer Grad im Backend hier sichtbar wird statt zu verschwinden. */
export function severityLabel(severity) {
    return SEVERITY[severity]?.label ?? severity;
}

export function severityClass(severity) {
    return SEVERITY[severity]?.cls ?? SEVERITY_FALLBACK;
}

export function categoryLabel(category) {
    return CATEGORY[category] ?? category;
}
