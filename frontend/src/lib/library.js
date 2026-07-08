/**
 * Reine Helfer für die Artefaktbibliothek (`/library`, Phase 18, Schritt 3).
 *
 * DOM-nahe Aktionen (PNG-Konvertierung, Datei-Download) liegen in der Seite; hier nur
 * pure, testbare Formatierung/Zuordnung.
 */

// Feingranulares `kind` → deutsches Anzeige-Label.
export const KIND_LABELS = {
    image: 'Bild',
    circuit: 'Schaltplan',
    plot: 'Funktionsgraph',
    mermaid: 'Diagramm',
    ggb: 'GeoGebra',
    document: 'Dokument',
};

export function kindLabel(kind) {
    return KIND_LABELS[kind] ?? kind;
}

const MIME_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/svg+xml': 'svg',
    'application/vnd.geogebra.file': 'ggb',
};

export function mimeExt(mime) {
    return MIME_EXT[mime] ?? 'bin';
}

// Dateiendung für den rohen Quelltext (Prompt bzw. Diagramm-Code).
const CODE_EXT = { circuit: 'tex', plot: 'yaml', mermaid: 'mmd', image: 'txt' };

export function codeExt(kind) {
    return CODE_EXT[kind] ?? 'txt';
}

// Byte-Zahl → menschenlesbar (deutsche Dezimalkomma-Schreibweise).
export function formatBytes(n) {
    if (n == null) return '';
    if (n < 1024) return `${n} B`;
    const kb = n / 1024;
    if (kb < 1024) return `${_num(kb)} KB`;
    return `${_num(kb / 1024)} MB`;
}

function _num(v) {
    return v.toFixed(v < 10 ? 1 : 0).replace('.', ',');
}

// Belegung in Prozent (0–100), gedeckelt.
export function usagePercent(used, quota) {
    if (!quota || quota <= 0) return 0;
    return Math.min(100, Math.round((used / quota) * 100));
}

export function isSvg(mime) {
    return mime === 'image/svg+xml';
}

export function isImageLike(mime) {
    return typeof mime === 'string' && mime.startsWith('image/');
}

const _UMLAUTS = { ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' };

// Titel → sicherer Dateiname-Stamm.
export function slugify(title) {
    const s = (title || 'artefakt')
        .toLowerCase()
        .replace(/[äöüß]/g, (c) => _UMLAUTS[c])
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 60);
    return s || 'artefakt';
}
