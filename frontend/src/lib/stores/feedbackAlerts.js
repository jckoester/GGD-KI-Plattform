import { writable, get } from "svelte/store";
import { getAdminFeedback } from "$lib/api.js";
import { user } from "./user.js";

/** Wie viele Rückmeldungen noch Arbeit machen — für den Zähler in der Admin-Navigation. */
export const offeneFeedbackCount = writable(0);

/**
 * Holt den Zähler neu.
 *
 * Ohne Abfrageschleife: Rückmeldungen treffen einzeln über den Tag verteilt ein, nicht
 * im Minutentakt. Geholt wird beim Laden und nach jedem Statuswechsel — das genügt,
 * und ein Zähler, der eine Minute alt ist, hat noch niemanden in die Irre geführt.
 */
export async function refreshFeedbackAlerts() {
    if (!get(user)?.roles?.includes("admin")) return;
    try {
        // `limit=1`, weil nur die Zähler gebraucht werden — die Liste selbst nicht.
        const daten = await getAdminFeedback({ limit: 1 });
        const zaehler = daten.counts ?? {};
        offeneFeedbackCount.set((zaehler.open ?? 0) + (zaehler.in_progress ?? 0));
    } catch {
        // Der Zähler ist informativ — ein Fehler darf die Navigation nicht aufhalten.
    }
}
