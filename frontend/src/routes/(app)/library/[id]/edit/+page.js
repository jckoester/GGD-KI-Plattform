import { redirect } from '@sveltejs/kit';

/** Seit 0.40 unter `/workshop/<id>/edit` (siehe `library/+page.js`). */
export function load({ params, url }) {
    throw redirect(301, `/workshop/${encodeURIComponent(params.id)}/edit${url.search}`);
}
