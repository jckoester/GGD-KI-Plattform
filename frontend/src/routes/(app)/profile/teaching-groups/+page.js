import { redirect } from '@sveltejs/kit';

/**
 * Die Seite ist am 25.09.2026 zu `/teaching` gewandert (Paket 7, AP6).
 *
 * Sie saß im Profil, gehörte aber nicht dorthin: Kürzel, Abgleich und Gruppen sind
 * Unterrichts-Einstellungen, die man in der Regel zu Schuljahresbeginn einmal trifft —
 * mit dem Benutzerprofil haben sie nichts zu tun. Die Weiterleitung steht hier, damit
 * Lesezeichen und ältere Links nicht ins Leere laufen.
 */
export function load() {
    throw redirect(301, '/teaching');
}
