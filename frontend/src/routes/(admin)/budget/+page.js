import { get } from 'svelte/store'
import { redirect } from '@sveltejs/kit'
import { user } from '$lib/stores/user.js'

export function load() {
    const $user = get(user)
    if (!$user?.roles.some((r) => ['budget', 'admin'].includes(r))) {
        redirect(302, '/')
    }
    return {
        title: 'Budget',
        headerColor: 'bg-amber-700 dark:bg-amber-900',
    }
}
