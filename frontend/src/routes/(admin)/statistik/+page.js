import { get } from 'svelte/store'
import { redirect } from '@sveltejs/kit'
import { user } from '$lib/stores/user.js'

export function load() {
    const $user = get(user)
    if (!$user?.roles.some((r) => ['statistics', 'admin'].includes(r))) {
        redirect(302, '/')
    }
    return {
        title: 'Statistik',
        headerColor: 'bg-teal-700 dark:bg-teal-900',
    }
}
