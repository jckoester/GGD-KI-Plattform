import { redirect } from '@sveltejs/kit'
import { nutzer } from '$lib/zugang.js'

// Liegt seit 0.27 in der Routengruppe `(admin)` (Adresse unverändert): Verwaltung und Editor
// stehen im Admin-Layout, neben „Assistenten-Freigabe“ (Plan F8, Jan 01.11.2026).
export async function load() {
  const $user = await nutzer()
  if (!$user?.roles.includes('admin')) redirect(302, '/assistants')
  return { title: 'Assistenten verwalten', sidebarSection: 'settings' }
}
