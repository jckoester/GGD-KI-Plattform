/**
 * Das Inhaltsverzeichnis der Hilfe (Paket 8, AP1/AP2).
 *
 * ⚠️ **Kuratiert, nicht erzeugt** (Entscheidung Jan, 26.09.2026). Aus den Dateinamen
 * abgeleitet stünde „Bibliothek" vor „Erste Schritte" — die Reihenfolge ist eine
 * redaktionelle Entscheidung, sie führt vom Einstieg zu den Einzelthemen. Erzeugt wird
 * nur die **Vollständigkeit**: `help_nav.test.js` hält diese Liste gegen `docs/user/`,
 * in beide Richtungen.
 *
 * ⚠️ **Warum das nötig wurde:** Bis zum 26.09.2026 kostete jede Seite ein eigenes
 * Verzeichnis mit einer `+page.svelte`, die immer dasselbe tat. Acht von achtzehn
 * Dokumenten hatten keins und waren in der Anwendung unerreichbar — darunter
 * `stundenplan.md`, das vier Tage zuvor deutlich erweitert worden war. Wer Doku
 * schreibt, schreibt sie in `docs/user/` und merkt nicht, dass sie nicht ankommt.
 *
 * Felder:
 * - `fuer` — für wen der Eintrag im Verzeichnis **erscheint**. Die Seite selbst bleibt
 *   erreichbar: Sie ist nicht geheim, nur unpassend (F2).
 * - `geschuetzt` — die Ausnahme: Diese Seite weist Nicht-Admins ab. Sie beschreibt die
 *   Konfiguration der Guardrails und stand schon immer unter dieser Prüfung.
 */

export const helpNav = [
    { label: 'Übersicht',           slug: '',                    file: 'README' },
    { label: 'Erste Schritte',      slug: 'erste-schritte',      file: 'erste-schritte' },
    { label: 'Die ersten 30 Minuten', slug: 'erste-30-minuten',  file: 'erste-30-minuten', fuer: 'teacher' },
    { label: 'Für Schüler:innen',   slug: 'schueler',            file: 'schueler' },
    { label: 'Chat nutzen',         slug: 'chat',                file: 'chat' },
    { label: 'Assistenten',         slug: 'assistenten',         file: 'assistenten' },
    { label: 'Bilder erzeugen',     slug: 'bilder-erzeugen',     file: 'bilder-erzeugen' },
    { label: 'Diagramme & Graphen', slug: 'diagramme',           file: 'diagramme' },
    { label: 'Bibliothek',          slug: 'bibliothek',          file: 'bibliothek' },
    { label: 'Material-Werkstatt',  slug: 'werkstatt',           file: 'werkstatt' },
    { label: 'KI-Ergebnisse zitieren', slug: 'zitieren',         file: 'zitieren' },
    { label: 'Fächer und Gruppen',  slug: 'faecher',             file: 'faecher' },
    { label: 'Kontextspeicher',     slug: 'kontext',             file: 'kontext' },
    { label: 'Fachbegriffe pflegen', slug: 'fachbegriffe-pflegen', file: 'fachbegriffe-pflegen', fuer: 'teacher' },
    { label: 'Schulcurriculum',     slug: 'curriculum',          file: 'curriculum', fuer: 'teacher' },
    { label: 'Unterrichtsplanung',  slug: 'unterrichtsplanung',  file: 'unterrichtsplanung', fuer: 'teacher' },
    { label: 'Stundenplan übernehmen', slug: 'stundenplan',      file: 'stundenplan', fuer: 'teacher' },
    { label: 'Profil & Budget',     slug: 'profil',              file: 'profil' },
    { label: 'Feedback geben',      slug: 'feedback',            file: 'feedback' },
    { label: 'Datenschutz',         slug: 'datenschutz',         file: 'datenschutz' },
    { label: 'Inhaltsrichtlinien',  slug: 'guardrails',          file: 'guardrails', fuer: 'admin', geschuetzt: true },
].map((e) => ({ ...e, path: e.slug ? `/help/${e.slug}` : '/help' }))

/** Der Eintrag zu einem Pfadstück — `''` ist die Übersicht. */
export function helpEintrag(slug) {
    return helpNav.find((e) => e.slug === (slug ?? '')) ?? null
}

/**
 * Das Verzeichnis für diese Rolle.
 *
 * ⚠️ **Nur das Verzeichnis, nicht der Zugang.** Eine Schülerin, die „Schulcurriculum"
 * und „Stundenplan übernehmen" gelistet sieht, sucht nach Funktionen, die es für sie
 * nicht gibt. Wer den Pfad kennt, liest die Seite trotzdem — dafür gibt es `geschuetzt`,
 * und das steht an genau einer Seite.
 */
export function sichtbareHilfe(rollen) {
    const hat = (r) => (rollen ?? []).includes(r)
    return helpNav.filter((e) => {
        if (e.fuer === 'admin') return hat('admin')
        if (e.fuer === 'teacher') return hat('teacher') || hat('admin')
        return true
    })
}
