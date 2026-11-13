import { redirect } from '@sveltejs/kit';

/**
 * Seit 0.41 hat jedes Produkt eine Ansicht unter `/workshop/<id>`; der Editor eines Dokuments
 * ist dort eingebaut. Die alte Editor-Adresse leitet um.
 */
export function load({ params, url }) {
    throw redirect(301, `/workshop/${encodeURIComponent(params.id)}${url.search}`);
}
