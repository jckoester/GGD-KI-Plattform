import { get, writable, derived } from "svelte/store";
import { getCalendarStatus } from "$lib/api.js";

// `null` = noch nicht gefragt. Bewusst nicht `false`: Sonst blitzt der Menüpunkt bei jedem
// Laden kurz auf und verschwindet wieder — oder umgekehrt. Erst nach der Antwort wird
// entschieden.
const _status = writable({ configured: null });

/** Schreibgeschützt: Ist eine Stundenplanquelle eingerichtet? */
export const calendarStatus = derived(_status, ($s) => $s);

/** True nur, wenn die Antwort da ist UND eine Quelle eingerichtet ist. */
export const calendarConfigured = derived(_status, ($s) => $s.configured === true);

/** Lädt den Status **einmal**, falls noch nicht gefragt.
 *
 * Für Stellen, die den Status nur *lesen* und nicht wissen können, ob ihn jemand vorher
 * geholt hat. Bis 14.09.2026 riefen ihn ausschließlich die Admin-Seitenleiste und
 * `/settings` — beide in der `(admin)`-Routengruppe. Der Wochenmuster-Editor liegt unter
 * `(app)` und las damit dauerhaft den Anfangswert: `configured === null`, also `false`.
 * Sein Knopf „Aus Stundenplan übernehmen" erschien nie, obwohl der Stundenplan
 * eingerichtet war.
 *
 * Der Unterschied zu `refreshCalendarStatus`: Das hier fragt höchstens einmal und ist
 * deshalb gefahrlos aus jeder Komponente aufrufbar; jenes erzwingt eine neue Antwort und
 * gehört dorthin, wo sich die Einrichtung gerade geändert haben kann.
 */
export async function ensureCalendarStatus() {
  if (get(_status).configured === null) await refreshCalendarStatus();
}

export async function refreshCalendarStatus() {
  try {
    _status.set(await getCalendarStatus());
  } catch {
    // Bei Netzwerkfehler bleibt es beim bisherigen Stand. Ein Fehlschlag darf einen
    // eingerichteten Kalender nicht aus der Navigation entfernen — das sähe aus wie
    // „abgeschaltet" und war schon einmal die Ursache eines Rätsels (Kürzel-Feld).
  }
}
