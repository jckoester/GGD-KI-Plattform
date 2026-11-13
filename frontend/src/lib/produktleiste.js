/**
 * Wörter der Produktleiste im Chat (0.41, Schritt 7) — eine Stelle für Bild, Diagramm und Text.
 *
 * Bis dahin hieß derselbe Knopf über dem Bild „In der Werkstatt speichern“ (nur als Titel),
 * am Diagramm „In Werkstatt“ und unter dem Text gab es ihn gar nicht. Ein Zustand, ein Wort.
 */

const KNOPF = {
    idle: 'Speichern',
    saving: 'Speichert…',
    saved: 'Gespeichert',
    exists: 'Schon da',
    full: 'Werkstatt voll',
    error: 'Fehler',
};

const TITEL = {
    idle: 'In der Werkstatt speichern',
    saving: 'Wird gespeichert…',
    saved: 'In der Werkstatt gespeichert',
    exists: 'Bereits in der Werkstatt',
    full: 'Werkstatt voll — bitte zuerst aufräumen',
    error: 'Speichern fehlgeschlagen',
};

/**
 * @param {'idle'|'saving'|'saved'|'exists'|'full'|'error'} zustand
 * @param {'knopf'|'titel'} wo
 */
export function speicherText(zustand, wo = 'knopf') {
    const tabelle = wo === 'titel' ? TITEL : KNOPF;
    return tabelle[zustand] ?? tabelle.idle;
}

/** Dateiname für eine Textantwort als Markdown. */
export function textDateiname(titel) {
    const slug = (titel || 'antwort')
        .toLowerCase()
        .normalize('NFKD').replace(/[̀-ͯ]/g, '')
        .replace(/ß/g, 'ss')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 60);
    return `${slug || 'antwort'}.md`;
}
