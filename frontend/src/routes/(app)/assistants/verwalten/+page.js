import { get } from 'svelte/store'
import { redirect } from '@sveltejs/kit'
import { user } from '$lib/stores/user.js'

export function load() {
  const $user = get(user)
  if (!$user?.roles.includes('admin')) redirect(302, '/assistants')
  return { title: 'Assistenten verwalten' }
}
