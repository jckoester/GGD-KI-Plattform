/**
 * Rückweg aus dem Parameter `?back=` (0.47.1).
 *
 * ⚠️ **Der Parameter kommt aus der Adresse, also von wem auch immer den Link gebaut hat.**
 * Ungeprüft im `href` führte `?back=javascript:…` beim Klick auf „Zurück“ Skript im Namen
 * der angemeldeten Person aus, und `?back=//fremde.seite` war eine offene Weiterleitung.
 * Svelte prüft `href` nicht. Deshalb liest jede Seite `back` nur über diese Funktion
 * (Wächter: `rueckweg.test.js`).
 */

const PRUEFBASIS = 'http://rueckweg.invalid'

/**
 * Der Wert, wenn er ein Pfad der Plattform ist, sonst `null`.
 *
 * Erlaubt sind nur Pfade mit genau einem führenden `/`. Zusätzlich muss der Pfad, wie ihn
 * der Browser auflöst, auf derselben Seite bleiben — das fängt `/\fremd`, `/<Tab>/fremd`
 * und Ähnliches, was ein Browser zu `//fremd` macht.
 *
 * @param {string|null|undefined} wert
 * @returns {string|null}
 */
export function sichererRueckweg(wert) {
    if (typeof wert !== 'string' || !wert.startsWith('/')) return null
    if (wert.startsWith('//') || wert.startsWith('/\\')) return null
    // Steuerzeichen und Leerraum: Browser entfernen Tab und Zeilenumbruch aus Adressen.
    // eslint-disable-next-line no-control-regex
    if (/[\u0000- \u007f]/.test(wert)) return null
    try {
        if (new URL(wert, PRUEFBASIS).origin !== PRUEFBASIS) return null
    } catch {
        return null
    }
    return wert
}

/**
 * `back` aus den Parametern einer Adresse, geprüft.
 *
 * @param {URLSearchParams} params
 * @returns {string|null}
 */
export function rueckwegAus(params) {
    return sichererRueckweg(params?.get('back'))
}
