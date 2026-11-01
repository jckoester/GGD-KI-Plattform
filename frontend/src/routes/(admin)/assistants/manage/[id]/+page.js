import { redirect } from '@sveltejs/kit'
import { nutzer } from '$lib/zugang.js'

// ⚠️ Bis 0.27 ohne Rollenprüfung: Der Editor bekommt hier fest `isAdmin={true}` — eine
// Lehrkraft, die die Adresse kannte, sah die Admin-Schalter. Lehrkräfte bearbeiten ihre
// eigenen Assistenten unter `/assistants/my/[id]`.
export async function load({ params }) {
  const $user = await nutzer()
  if (!$user?.roles.includes('admin')) redirect(302, '/assistants/my')
  return { id: params.id, title: 'Assistent bearbeiten', sidebarSection: 'settings' }
}
