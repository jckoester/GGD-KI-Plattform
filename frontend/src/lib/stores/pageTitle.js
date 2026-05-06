import { writable } from 'svelte/store'

export const pageTitle = writable('')
export const activeConversationId = writable(null)
export const activeConversationSubjectId = writable(null)
export const activeConversationGroupId = writable(null)