import { error, redirect } from '@sveltejs/kit';
import { get } from 'svelte/store';

import { helpEintrag } from '$lib/help-nav.js';
import { user } from '$lib/stores/user.js';

/**
 * Eine Route für alle Hilfeseiten (Paket 8, AP1).
 *
 * ⚠️ **Vorher kostete jede Seite ein eigenes Verzeichnis** mit einer `+page.svelte`, die
 * immer dasselbe tat. Acht Dokumente hatten keins und waren damit unerreichbar, obwohl
 * sie geschrieben, gepflegt und im Inhaltsverzeichnis der Markdown-Übersicht verlinkt
 * waren.
 *
 * Unbekanntes Pfadstück → **404**, nicht stilles Nichts: Ein Tippfehler im Link soll
 * auffallen. Welche Pfade es gibt, sagt `helpNav`.
 */
export function load({ params }) {
    const eintrag = helpEintrag(params.seite);
    if (!eintrag) error(404, 'Diese Hilfeseite gibt es nicht.');

    // Die eine Ausnahme: Die Guardrail-Seite beschreibt Konfiguration und stand schon
    // immer unter dieser Prüfung. Alle übrigen sind nur *gefiltert*, nicht gesperrt.
    if (eintrag.geschuetzt && !get(user)?.roles?.includes('admin')) {
        redirect(302, '/help');
    }

    return { eintrag, title: eintrag.label };
}
