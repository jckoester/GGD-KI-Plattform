import { writable } from 'svelte/store';
import { getAdminAssistants } from '$lib/api.js';

export const pendingCount = writable(0);

export async function refreshPendingCount() {
  try {
    const result = await getAdminAssistants({ status: 'pending_review', limit: 1 });
    pendingCount.set(result.total ?? 0);
  } catch {
    // Fehler ignorieren — Sidebar-Badge ist nur informativ
  }
}
