import { writable } from 'svelte/store'

export const pageTitle = writable('')
export const activeConversationId = writable(null)
export const activeConversationSubjectId = writable(null)
export const activeConversationGroupId = writable(null)
// Der Assistent der offenen Konversation. Gebraucht vom Rückmelde-Formular, das den
// Kontext einer Meldung automatisch mitschickt: „im Chat, und zwar mit diesem
// Assistenten" ist die Angabe, die eine Fehlerbeschreibung überhaupt erst einordnet.
export const activeConversationAssistantId = writable(null)
