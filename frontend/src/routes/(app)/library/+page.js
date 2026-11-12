import { redirect } from '@sveltejs/kit';

/**
 * Seit 0.40 heißt der Bereich „Werkstatt“ und liegt unter `/workshop` (Päckchen AM). Die
 * Weiterleitung hält Lesezeichen und ältere Links am Leben — samt Filter (`?subject_id=`).
 */
export function load({ url }) {
    throw redirect(301, `/workshop${url.search}`);
}
