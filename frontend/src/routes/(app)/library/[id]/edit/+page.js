import { redirect } from '@sveltejs/kit';

/** Seit 0.40 in der Werkstatt, seit 0.41 als Produktansicht `/workshop/<id>` (siehe `library/+page.js`). */
export function load({ params, url }) {
    throw redirect(301, `/workshop/${encodeURIComponent(params.id)}${url.search}`);
}
