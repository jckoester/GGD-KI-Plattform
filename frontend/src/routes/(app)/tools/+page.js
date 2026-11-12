import { redirect } from '@sveltejs/kit';

/**
 * Die Seite „Werkzeuge“ gibt es seit 0.40 nicht mehr (Päckchen AM): Ein Werkzeug ist ein
 * Assistent mit der Angabe „stellt her“, und die Assistentenliste filtert danach. Die
 * Weiterleitung hält Lesezeichen und ältere Links am Leben.
 */
export function load() {
    throw redirect(301, '/assistants?erstellt=alle');
}
