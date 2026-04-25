import { writable, derived } from 'svelte/store'

export const user = writable(null)
// { pseudonym, roles: string[], grade, display_name }

/** true wenn der User mindestens eine der genannten Rollen hat */
export const hasAnyRole = (roles) =>
    derived(user, ($u) => !!$u && roles.some((r) => $u.roles.includes(r)))

/** true wenn der User die genannte Rolle hat */
export const hasRole = (role) =>
    derived(user, ($u) => !!$u && $u.roles.includes(role))
