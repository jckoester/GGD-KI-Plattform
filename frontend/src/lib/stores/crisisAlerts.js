import { writable, derived, get } from "svelte/store";
import { getFlagSummary, getPendingRequestCount } from "$lib/api.js";
import { user } from "./user.js";

// Zähler noch nicht abgeschlossener Krisen-Fälle, rollenabhängig.
// admin:  offene (neue, noch unbearbeitete) + laufende (in Prüfung) Flags
// review: offene Einsicht-Anträge, die auf Zweitfreigabe warten
export const openFlagCount = writable(0); // status 'open'
export const inReviewFlagCount = writable(0); // status 'under_review'
export const pendingRequestCount = writable(0);

// Gesamtzahl für den dezenten Marker am Avatar — sinkt erst, wenn ein Fall
// tatsächlich abgeschlossen ist (nicht schon beim Beantragen der Einsicht).
export const crisisAlertTotal = derived(
  [openFlagCount, inReviewFlagCount, pendingRequestCount],
  ([$open, $inReview, $pending]) => $open + $inReview + $pending,
);

export async function refreshCrisisAlerts() {
  const u = get(user);
  if (!u?.roles) return;
  if (u.roles.includes("admin")) {
    try {
      const s = await getFlagSummary();
      openFlagCount.set(s.open ?? 0);
      inReviewFlagCount.set(s.in_review ?? 0);
    } catch {
      // Badge ist nur informativ — Fehler still ignorieren
    }
  }
  if (u.roles.includes("review")) {
    try {
      pendingRequestCount.set((await getPendingRequestCount()).count ?? 0);
    } catch {
      // s. o.
    }
  }
}
