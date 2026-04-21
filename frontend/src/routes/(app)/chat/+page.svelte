<script>
  import { Send, Loader2, AlertCircle } from 'lucide-svelte'
  import { goto } from '$app/navigation'
  import { page } from '$app/stores'
  import { streamChat, ApiError, getConversationMessages } from '$lib/api.js'
  import { refreshConversations } from '$lib/stores/conversations.js'
  import { user } from '$lib/stores/user.js'
  import { onMount } from 'svelte'

  let messages = $state([])
  let input = $state('')
  let textarea = $state(null)
  let isStreaming = $state(false)
  let error = $state(null)
  let scrollAnchor = $state(null)
  let conversationId = $state(null)
  let loadingConversation = $state(false)
  let conversationError = $state(null)

  let textAreaRows = $state(1)

  function adjustTextareaHeight() {
    if (!textarea) return
    // Direktes DOM-Reset nötig: reaktiver State-Update ist async,
    // scrollHeight würde sonst noch die alte Höhe liefern.
    textarea.rows = 1
    const rows = Math.min(Math.ceil(textarea.scrollHeight / 24), 6)
    textarea.rows = rows
    textAreaRows = rows
  }

  async function handleSubmit() {
    if (!input.trim() || isStreaming) return

    const userMessage = input.trim()
    input = ''
    adjustTextareaHeight()

    // Add user message
    messages = [...messages, { role: 'user', content: userMessage }]
    
    // Add placeholder for assistant response
    const assistantIndex = messages.length
    messages = [...messages, { role: 'assistant', content: '' }]
    
    isStreaming = true
    error = null

    try {
      // Nur user/assistant-Nachrichten senden — error-Einträge sind reine UI-Elemente
      const apiMessages = messages
        .slice(0, assistantIndex)
        .filter(m => m.role === 'user' || m.role === 'assistant')

      for await (const item of streamChat(apiMessages, conversationId)) {
        // Start-Event mit conversationId
        if (item.type === 'start') {
          conversationId = item.conversationId
          continue
        }
        // Token von Assistant
        messages[assistantIndex] = {
          ...messages[assistantIndex],
          content: messages[assistantIndex].content + item
        }
        messages = messages
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await goto('/')
        return
      }

      // Leeren Assistent-Placeholder entfernen, falls kein Token ankam
      if (messages[assistantIndex]?.content === '') {
        messages = [...messages.slice(0, assistantIndex), ...messages.slice(assistantIndex + 1)]
      }

      const knownErrors = {
        0:   'Verbindung zum Server fehlgeschlagen.',
        429: 'Dein Budget ist erschöpft.',
        502: 'Der KI-Dienst ist gerade nicht erreichbar.',
        503: 'Der KI-Dienst ist vorübergehend nicht verfügbar.',
      }
      const errorMessage = (err instanceof ApiError && knownErrors[err.status])
        ? knownErrors[err.status]
        : (err.message ?? 'Ein unbekannter Fehler ist aufgetreten.')

      messages = [...messages, { role: 'error', content: errorMessage }]
    } finally {
      isStreaming = false
      // Konversationen in Sidebar neu laden
      triggerSidebarRefresh()
    }
  }

  function handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  function handleInput() {
    adjustTextareaHeight()
  }

  // Laden der Konversation basierend auf URL-Parameter
  async function loadConversation() {
    const id = $page.url.searchParams.get('id')
    conversationError = null
    
    if (id) {
        loadingConversation = true
        try {
            const data = await getConversationMessages(id)
            messages = data.messages.map(m => ({ role: m.role, content: m.content }))
            conversationId = data.id
        } catch (err) {
            if (err instanceof ApiError) {
                conversationError = err.message
                // Bei 403 oder 404: Konversation nicht gefunden
                if (err.status === 403 || err.status === 404) {
                    messages = []
                    conversationId = null
                }
            } else {
                conversationError = 'Fehler beim Laden der Konversation'
            }
        } finally {
            loadingConversation = false
        }
    } else {
        // Neue Konversation
        messages = []
        conversationId = null
        conversationError = null
    }
  }

  // Reagieren auf URL-Änderungen
  $effect(() => {
    $page.url
    loadConversation()
  })

  // Automatisch Konversationen neu laden nach Stream-Ende
  // (wird aus Sidebar aufgerufen via refreshConversations)
  function triggerSidebarRefresh() {
    const limit = $user?.preferences?.sidebar_recent_chats_limit ?? 10
    refreshConversations(limit)
  }

  // Scroll to bottom when messages change (aber nicht beim initialen Laden)
  $effect(() => {
    messages
    if (!loadingConversation) {
      requestAnimationFrame(() => {
        if (scrollAnchor) {
          scrollAnchor.scrollIntoView({ behavior: 'smooth', block: 'end' })
        }
      })
    }
  })

</script>

<div class="h-full flex flex-col">
  <div class="flex-1 overflow-y-auto px-4 py-4">
    {#if loadingConversation}
      <div class="flex items-center justify-center h-full">
        <div class="flex flex-col items-center gap-2 text-gray-500">
          <Loader2 class="w-6 h-6 animate-spin" />
          <p>Konversation wird geladen...</p>
        </div>
      </div>
    {:else if conversationError}
      <div class="flex items-center justify-center h-full">
        <div class="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-red-600 max-w-md">
          <p class="flex items-center gap-2">
            <AlertCircle class="w-5 h-5 flex-shrink-0" />
            {conversationError}
          </p>
        </div>
      </div>
    {:else if messages.length === 0}
      <div class="flex items-center justify-center h-full">
        <div class="text-center text-gray-500">
          <p class="text-lg">Womit kann ich helfen?</p>
        </div>
      </div>
    {:else}
      <div class="space-y-4 max-w-4xl mx-auto">
        {#each messages as message, i}
          {#if message.role === 'user'}
            <div class="flex justify-end">
              <div class="bg-blue-500 text-white rounded-xl rounded-br-none px-4 py-2 max-w-[80%]">
                <p class="whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          {:else if message.role === 'assistant'}
            <div class="flex justify-start">
              <div class="bg-gray-100 dark:bg-gray-800 rounded-xl rounded-bl-none px-4 py-2 max-w-[80%]">
                <p class="whitespace-pre-wrap">{message.content}</p>
                {#if isStreaming && i === messages.length - 1}
                  <span class="animate-pulse cursor-default">|</span>
                {/if}
              </div>
            </div>
          {:else if message.role === 'error'}
            <div class="w-full">
              <div class="bg-red-50 border border-red-200 rounded-lg px-4 py-2 text-red-600">
                <p class="whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
    <div bind:this={scrollAnchor} class="h-0"></div>
  </div>

  <div class="flex-shrink-0 px-4 pb-4">
    <div class="flex gap-2 max-w-4xl mx-auto">
      <textarea
        bind:this={textarea}
        rows={textAreaRows}
        onkeydown={handleKeydown}
        oninput={handleInput}
        bind:value={input}
        disabled={isStreaming}
        placeholder={isStreaming ? '' : 'Nachricht eingeben...'}
        class="flex-1 resize-none rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-blue-500"
      ></textarea>
      <button
        onclick={handleSubmit}
        disabled={isStreaming || !input.trim()}
        class="p-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:bg-blue-300 disabled:cursor-not-allowed transition-colors flex items-center justify-center min-w-[44px]"
      >
        {#if isStreaming}
          <Loader2 class="w-5 h-5 animate-spin" />
        {:else}
          <Send class="w-5 h-5" />
        {/if}
      </button>
    </div>
  </div>
</div>
