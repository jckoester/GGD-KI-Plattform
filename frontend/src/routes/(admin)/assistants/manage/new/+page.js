import { redirect } from '@sveltejs/kit'
import { nutzer } from '$lib/zugang.js'

export async function load() {
  const $user = await nutzer()
  if (!$user?.roles.includes('admin')) redirect(302, '/assistants/my')
  return { title: 'Neuer Assistent', sidebarSection: 'settings' }
}
