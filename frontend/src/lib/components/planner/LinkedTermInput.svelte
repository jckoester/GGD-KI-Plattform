<script>
  /**
   * Einzelwert-Combobox für kontrolliertes Vokabular (Methode/Sozialform).
   * Pendant zur MaterialCell, aber Einzelwert statt Liste.
   *
   * value: LessonLinkedItem | null  → { typ:'text', wert } | { typ:'node', node_id, titel }
   *
   * - Tippen filtert Vorschläge (Knoten des contentType, Titel+Alias via /context/nodes).
   * - Auswahl eines Vorschlags → Knoten-Verlinkung (typ:'node').
   * - Enter ohne Auswahl bzw. Verlassen des Felds → Freitext (typ:'text').
   * - „+ '…' anlegen" legt einen neuen, zunächst privaten Vokabel-Knoten an und verlinkt ihn.
   */
  import { getContextNodes, createContextNode } from '$lib/api.js'

  let { value = null, contentType, subjectId = null, placeholder = '', onChange } = $props()

  let draft = $state('') // wird vom $effect aus value synchronisiert
  let dropdownOpen = $state(false)
  let items = $state([])
  let loading = $state(false)
  let creating = $state(false)
  let activeIdx = $state(0)
  let debounce = null

  const isNode = $derived(value?.typ === 'node')

  // Externe Wertänderung (z. B. Laden) in den Entwurf übernehmen.
  $effect(() => {
    if (value?.typ === 'text') draft = value.wert ?? ''
    else if (!value) draft = ''
  })

  const exactMatch = $derived(
    items.find((n) => n.title.toLowerCase() === draft.trim().toLowerCase()) ?? null,
  )

  function closeDropdown() {
    dropdownOpen = false
    items = []
    activeIdx = 0
  }

  function commitText() {
    if (value?.typ === 'node') return // bereits ein Knoten gewählt — nicht überschreiben
    const v = draft.trim()
    onChange(v ? { typ: 'text', wert: v } : null)
    closeDropdown()
  }

  function pickNode(node) {
    onChange({ typ: 'node', node_id: node.id, titel: node.title })
    closeDropdown()
  }

  function clear() {
    onChange(null)
    draft = ''
    closeDropdown()
  }

  function onInput() {
    const q = draft.trim()
    clearTimeout(debounce)
    if (!q) {
      closeDropdown()
      return
    }
    debounce = setTimeout(() => search(q), 250)
  }

  async function search(q) {
    loading = true
    dropdownOpen = true
    try {
      const params = { content_type: contentType, q, limit: 8 }
      if (subjectId) params.subject_id = subjectId
      const res = await getContextNodes(params)
      items = Array.isArray(res) ? res : (res.items ?? [])
      activeIdx = 0
    } catch {
      items = []
    } finally {
      loading = false
    }
  }

  async function createNode() {
    const titel = draft.trim()
    if (!titel || creating) return
    creating = true
    try {
      const node = await createContextNode({
        category: 'knowledge',
        content_type: contentType,
        title: titel,
        read_scope: 'private',
        subject_id: subjectId ?? null,
      })
      pickNode(node)
    } catch {
      commitText() // Fallback: als Freitext behalten
    } finally {
      creating = false
    }
  }

  function onKeydown(e) {
    if (dropdownOpen && items.length) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        activeIdx = Math.min(activeIdx + 1, items.length - 1)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        activeIdx = Math.max(activeIdx - 1, 0)
        return
      }
      if (e.key === 'Enter') {
        e.preventDefault()
        pickNode(items[activeIdx])
        return
      }
      if (e.key === 'Escape') {
        closeDropdown()
        return
      }
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      commitText()
    }
  }
</script>

{#if isNode}
  <span class="text-xs flex items-center gap-1">
    <span class="text-primary dark:text-primary-dark" aria-hidden="true">⬡</span>
    <span class="text-light-tx dark:text-dark-tx truncate max-w-[140px]"
          title={value.titel || value.node_id}>{value.titel || value.node_id}</span>
    <button
      onclick={clear}
      class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re ml-auto"
      aria-label="Auswahl entfernen"
    >✕</button>
  </span>
{:else}
  <div class="relative">
    <input
      type="text"
      bind:value={draft}
      oninput={onInput}
      onkeydown={onKeydown}
      onblur={() => setTimeout(() => { closeDropdown(); commitText() }, 200)}
      {placeholder}
      class="w-full bg-transparent text-xs text-light-tx dark:text-dark-tx
             border-b border-transparent focus:border-primary dark:focus:border-primary-dark outline-none
             placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2"
    />

    {#if dropdownOpen}
      <div
        class="absolute top-full left-0 right-0 mt-1 z-50 min-w-[180px]
               bg-light-bg dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
               rounded-md shadow-xl max-h-56 overflow-y-auto"
      >
        {#if loading}
          <div class="px-3 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2">Suche…</div>
        {:else}
          {#each items as node, i}
            <button
              onmousedown={(e) => { e.preventDefault(); pickNode(node) }}
              class="w-full px-3 py-1.5 text-left text-xs flex items-center gap-2 transition-colors
                     {i === activeIdx ? 'bg-light-ui-2 dark:bg-dark-ui-2' : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
            >
              <span class="text-primary dark:text-primary-dark" aria-hidden="true">⬡</span>
              <span class="truncate text-light-tx dark:text-dark-tx">{node.title}</span>
            </button>
          {/each}
          {#if draft.trim() && !exactMatch}
            <button
              onmousedown={(e) => { e.preventDefault(); createNode() }}
              disabled={creating}
              class="w-full px-3 py-1.5 text-left text-xs border-t border-light-ui-3 dark:border-dark-ui-3
                     text-light-bl dark:text-dark-bl hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-50"
            >+ „{draft.trim()}" anlegen</button>
          {/if}
          {#if !loading && items.length === 0 && !draft.trim()}
            <div class="px-3 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2">Tippen zum Suchen …</div>
          {/if}
        {/if}
      </div>
    {/if}
  </div>
{/if}
