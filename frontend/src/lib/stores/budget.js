import { writable } from 'svelte/store'

export const budget = writable(null)
// null = noch nicht geladen oder nicht verfügbar
// { max_budget_eur, spend_eur, remaining_eur, budget_duration, eur_usd_rate, ... }

export async function refreshBudget() {
  const { getBudget } = await import('$lib/api.js')
  const data = await getBudget()
  budget.set(data)
}
