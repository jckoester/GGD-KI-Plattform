/**
 * Reine Helfer für die Werkstatt (`/workshop`, bis 0.40 `/library`; Phase 18, Schritt 3).
 *
 * DOM-nahe Aktionen (PNG-Konvertierung, Datei-Download) liegen in der Seite; hier nur
 * pure, testbare Formatierung/Zuordnung.
 */

// Feingranulares `kind` → deutsches Anzeige-Label.
export const KIND_LABELS = {
    image: 'Bild',
    circuit: 'Schaltplan',
    plot: 'Funktionsgraph',
    smiles: 'Strukturformel',
    mermaid: 'Diagramm',
    ggb: 'GeoGebra',
    document: 'Dokument',
    export_pdf: 'PDF',
    export_docx: 'Word',
    export_odt: 'ODT',
};

export function kindLabel(kind) {
    return KIND_LABELS[kind] ?? kind;
}

const MIME_EXT = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/svg+xml': 'svg',
    'application/vnd.geogebra.file': 'ggb',
    'text/markdown': 'md',
    'application/pdf': 'pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.oasis.opendocument.text': 'odt',
};

export function mimeExt(mime) {
    return MIME_EXT[mime] ?? 'bin';
}

// Dateiendung für den rohen Quelltext (Prompt bzw. Diagramm-Code).
const CODE_EXT = { circuit: 'tex', plot: 'yaml', smiles: 'smi', mermaid: 'mmd', image: 'txt' };

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
    const s = (title || 'produkt')
        .toLowerCase()
        .replace(/[äöüß]/g, (c) => _UMLAUTS[c])
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 60);
    return s || 'produkt';
}

// ── Ordnung der Werkstatt (0.41, Schritt 4) ─────────────────────────────────

/**
 * Die Arten im Filter. Bild, Diagramm, Dokument kommen mit ihrer Beschriftung aus der
 * gemeinsamen Liste „stellt her“ (`$lib/produktarten.js`) — dieselben Kennungen wie im
 * Backend (`app/assistants/produkte.py`, `WERKSTATT_ARTEN`); dazu „Dateien“ für GeoGebra und
 * Exporte, die es nur hier gibt.
 *
 * @param {Array<{id: string, filter: string}>} produktarten
 */
export function werkstattArten(produktarten) {
    const aus_liste = ['image', 'diagram', 'document']
        .map((id) => (produktarten ?? []).find((p) => p.id === id))
        .filter(Boolean)
        .map((p) => ({ id: p.id, label: p.filter }));
    return [...aus_liste, { id: 'file', label: 'Dateien' }];
}

export const SORTIERUNGEN = [
    { id: 'updated', label: 'Zuletzt bearbeitet' },
    { id: 'created', label: 'Zuletzt angelegt' },
    { id: 'title', label: 'Titel' },
];

/** Schlüssel in den Einstellungen der Person (F10): Sortierung und Gruppierung. */
export const ANSICHT_SCHLUESSEL = 'werkstatt_ansicht';

/** Gemerkte Ansicht — Unbekanntes fällt auf die Vorgabe „zuletzt bearbeitet, ungruppiert“. */
export function ansichtAusEinstellungen(einstellungen) {
    const roh = einstellungen?.[ANSICHT_SCHLUESSEL] ?? {};
    return {
        sort: SORTIERUNGEN.some((s) => s.id === roh.sort) ? roh.sort : 'updated',
        gruppiert: roh.gruppiert === true,
    };
}

const ARTEN_IDS = new Set(['image', 'diagram', 'document', 'file']);

function ganzzahl(roh) {
    const zahl = roh == null ? NaN : Number(roh);
    return Number.isInteger(zahl) ? zahl : null;
}

/**
 * Filter aus der Adresszeile — Links (etwa „Produkte in Mathematik“ von der Fachseite) und
 * Zurück tragen ihn. Unbekanntes zählt als „kein Filter“.
 *
 * @param {URLSearchParams} params
 */
export function filterAusAdresse(params) {
    const art = params.get('art');
    return {
        q: (params.get('q') ?? '').trim(),
        art: ARTEN_IDS.has(art) ? art : null,
        subjectId: ganzzahl(params.get('subject_id')),
        topic: params.get('topic') || null,
        baldAblaufend: params.get('bald') === '1',
        alsBaustein: params.get('baustein') === '1',
    };
}

/** Die Adresse zu einem Filter (nur gesetzte Teile), mit führendem `?` oder leer. */
export function adresseAusFilter(f) {
    const p = new URLSearchParams();
    if (f.q) p.set('q', f.q);
    if (f.art) p.set('art', f.art);
    if (f.subjectId != null) p.set('subject_id', String(f.subjectId));
    if (f.topic) p.set('topic', f.topic);
    if (f.baldAblaufend) p.set('bald', '1');
    if (f.alsBaustein) p.set('baustein', '1');
    const s = p.toString();
    return s ? `?${s}` : '';
}

/** Ist irgendein Filter gesetzt? */
export function filterGesetzt(f) {
    return Boolean(f.q || f.art || f.subjectId != null || f.topic || f.baldAblaufend || f.alsBaustein);
}

/**
 * Produkte nach Fach gruppiert, Fächer alphabetisch, „Ohne Fach“ zuletzt. Innerhalb einer
 * Gruppe bleibt die Reihenfolge der Liste (also die gewählte Sortierung).
 *
 * @param {Array<{subject_id?: number|null}>} items
 * @param {Record<number, {name: string}>} faecher
 */
export function nachFachGruppiert(items, faecher) {
    const gruppen = new Map();
    for (const item of items ?? []) {
        const id = item.subject_id ?? null;
        if (!gruppen.has(id)) gruppen.set(id, []);
        gruppen.get(id).push(item);
    }
    const name = (id) => (id == null ? 'Ohne Fach' : (faecher?.[id]?.name ?? 'Unbekanntes Fach'));
    return [...gruppen.entries()]
        .map(([id, liste]) => ({ subjectId: id, name: name(id), items: liste }))
        .sort((a, b) => {
            if (a.subjectId == null) return 1;
            if (b.subjectId == null) return -1;
            return a.name.localeCompare(b.name, 'de');
        });
}
