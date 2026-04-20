import { writable } from 'svelte/store'

export const user = writable(null)
// { pseudonym, roles: string[], grade, display_name }
