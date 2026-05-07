import { writable, derived } from 'svelte/store'
import { getGroupsConfig } from '$lib/api.js'

const _config = writable({ allow_manual_teaching_groups: true })

/** Schreibgeschützter Config-Store. */
export const groupsConfig = derived(_config, $c => $c)

export async function refreshGroupsConfig() {
    try {
        const data = await getGroupsConfig()
        _config.set(data)
    } catch {
        // Fallback: manuelle Gruppen erlaubt (sicherer Default bei Netzwerkfehler)
    }
}
