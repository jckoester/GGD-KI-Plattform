import { writable, derived } from "svelte/store";
import { getCalendarStatus } from "$lib/api.js";

// `null` = noch nicht gefragt. Bewusst nicht `false`: Sonst blitzt der Menüpunkt bei jedem
// Laden kurz auf und verschwindet wieder — oder umgekehrt. Erst nach der Antwort wird
// entschieden.
const _status = writable({ configured: null });

/** Schreibgeschützt: Ist eine Stundenplanquelle eingerichtet? */
export const calendarStatus = derived(_status, ($s) => $s);

/** True nur, wenn die Antwort da ist UND eine Quelle eingerichtet ist. */
export const calendarConfigured = derived(_status, ($s) => $s.configured === true);

export async function refreshCalendarStatus() {
  try {
    _status.set(await getCalendarStatus());
  } catch {
    // Bei Netzwerkfehler bleibt es beim bisherigen Stand. Ein Fehlschlag darf einen
    // eingerichteten Kalender nicht aus der Navigation entfernen — das sähe aus wie
    // „abgeschaltet" und war schon einmal die Ursache eines Rätsels (Kürzel-Feld).
  }
}
