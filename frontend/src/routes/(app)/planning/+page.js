import { redirect } from '@sveltejs/kit';

/**
 * Eine Übersichtsseite „Planung“ gibt es nicht (0.42, F2): Der Menüpunkt führt je Gruppe in
 * den Planer und ins Archiv. Wer `/planning` aufruft, landet im Archiv.
 */
export function load() {
    throw redirect(307, '/planning/archive');
}
