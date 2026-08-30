import { writable } from 'svelte/store'

export const budget = writable(null)
// null = noch nicht geladen oder nicht verfügbar
// { max_budget_eur, spend_eur, remaining_eur, wochenbetrag_eur,
//   naechste_aufstockung (ISO-Datum|null), vorsprung_wochen, eur_usd_rate }
// Kein `budget_duration`/`budget_reset_at` mehr: Seit dem Wochenmodell wird nichts
// zurückgesetzt — das Guthaben wächst je Unterrichtswoche.

export async function refreshBudget() {
  const { getBudget } = await import('$lib/api.js')
  const data = await getBudget()
  budget.set(data)
}
