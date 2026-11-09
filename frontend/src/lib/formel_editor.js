/**
 * MathLive für den Formel-Dialog (0.38): erst beim ersten Öffnen laden, dann einrichten.
 *
 * Datenschutz: MathLive lädt Schriften und Klänge relativ zum eigenen Skript nach. Beides
 * ist abgeschaltet — die KaTeX-Schriften bringt `katex.min.css` im Layout mit, MathLive
 * nutzt dieselben Namen. Externe Adressen (CDN, Sprachausgabe über Amazon) stehen in
 * MathLive nur in Fehlermeldungen; `formel_editor.test.js` wacht über die Einstellungen.
 */

let geladen = null;

/** Lädt MathLive einmal und stellt es ein. @returns {Promise<typeof import('mathlive').MathfieldElement>} */
export function mathliveLaden() {
    geladen ??= import('mathlive').then(({ MathfieldElement }) => {
        einstellen(MathfieldElement);
        return MathfieldElement;
    });
    return geladen;
}

/** Klassenweite Einstellungen — ohne Netz, deutsches Komma, deutsche Texte. */
export function einstellen(MathfieldElement) {
    MathfieldElement.fontsDirectory = null;
    MathfieldElement.soundsDirectory = null;
    MathfieldElement.keypressSound = null;
    MathfieldElement.plonkSound = null;
    MathfieldElement.decimalSeparator = ',';
    MathfieldElement.locale = 'de';
}

// Kontextmenü: nur, was man zum Schreiben braucht — keine Farben, Schriftarten, Matrizen.
const MENUE = new Set(['cut', 'copy', 'paste', 'select-all']);

/** Einstellungen am einzelnen Feld, nachdem es im Dokument hängt. */
export function feldEinrichten(feld) {
    // Escape schaltet in MathLive in den LaTeX-Modus; im Dialog soll es schließen.
    feld.keybindings = feld.keybindings.filter((k) => k.key !== '[Escape]');
    feld.menuItems = feld.menuItems.filter((m) => MENUE.has(m.id));
    tottasteAbfangen(feld.shadowRoot, feld);
}

/**
 * Tottasten (`^` auf deutscher Tastatur) in Chrome und Vivaldi (Versuch 08.11.2026).
 *
 * 1. Chrome meldet `keydown key="Dead"` **vor** der Zusammensetzung. MathLive leitet das
 *    Zeichen dann aus dem Tastencode ab (`IntlBackslash` ist bei US-Belegung `\`), wechselt
 *    in den LaTeX-Modus, und aus `^2` wird `\^`. Das Zeichen selbst kommt ohnehin über die
 *    Composition-Ereignisse — das keydown erreicht MathLive darum nicht.
 * 2. `compositionend` bringt `^` samt Folgezeichen (`"^("`). Mehrere Zeichen auf einmal
 *    wertet MathLive falsch aus (die Klammer doppelt) — also einzeln weitergeben.
 *
 * Safari schickt das keydown erst während der Zusammensetzung und gibt `^` allein fest;
 * beides greift dort nicht.
 */
export function tottasteAbfangen(wurzel, feld) {
    wurzel.addEventListener('keydown', (e) => {
        if (e.key === 'Dead') e.stopImmediatePropagation();
    }, true);
    wurzel.addEventListener('compositionend', (e) => {
        const zeichen = [...(e.data ?? '')];
        if (zeichen.length < 2) return;
        e.stopImmediatePropagation();
        // MathLive aus dem Zusammensetzen holen: Vorschau entfernen, Zustand zurück.
        e.target.dispatchEvent(new CompositionEvent('compositionend', { data: '', bubbles: true, composed: true }));
        for (const z of zeichen) feld.executeCommand(['typedText', z, { simulateKeystroke: true }]);
    }, true);
}
