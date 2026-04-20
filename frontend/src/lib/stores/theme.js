import { writable } from 'svelte/store';
import { patchPreferences } from '$lib/api.js';

function createThemeStore() {
    const cached =
        typeof localStorage !== 'undefined'
            ? (localStorage.getItem('theme') ?? 'system')
            : 'system';

    const { subscribe, set: _set } = writable(cached);

    function set(value) {
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem('theme', value);
        }
        _set(value);
        // Optimistisch: localStorage sofort aktualisieren, PATCH im Hintergrund
        patchPreferences({ theme: value }).catch(() => {/* Fehler ignorieren */});
    }

    function syncFromServer(value) {
        // Wird beim App-Start einmalig aus DB-Wert gesetzt, ohne zu PATCHen
        if (typeof localStorage !== 'undefined') {
            localStorage.setItem('theme', value);
        }
        _set(value);
    }

    return { subscribe, set, syncFromServer };
}

export const themePref = createThemeStore();
