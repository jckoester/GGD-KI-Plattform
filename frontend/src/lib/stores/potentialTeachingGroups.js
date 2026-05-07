import { writable, derived } from 'svelte/store'
import { getPotentialTeachingGroups } from '$lib/api.js'

const _potential = writable([])

export const potentialTeachingGroups = derived(_potential, $p => $p)

export async function refreshPotentialTeachingGroups() {
    try {
        const data = await getPotentialTeachingGroups()
        _potential.set(data.items)
    } catch {
        // nicht-kritisch
    }
}
