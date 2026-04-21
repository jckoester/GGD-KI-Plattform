import { writable } from 'svelte/store'

export const pageTitle = writable('')
export const activeConversationId = writable(null)