<script>
  /**
   * Material-Zelle einer Phase: Kombination aus Freitext und Knoten-Verlinkung.
   *
   * Datenmodell (Array): { typ: 'text', wert } | { typ: 'node', node_id, titel }
   *
   * Eingabe in EINEM Feld:
   *   - Tippen + Enter            → Freitext-Eintrag
   *   - "@" am Feldanfang         → Knotensuche (Dropdown), Auswahl → Knoten-Eintrag
   *
   * Optionale „per Assistent erzeugen"-Aktion über onGenerate (klar getrennt).
   */
  import { CONTENT_TYPE_LABELS } from '$lib/taxonomy.js'

  let { material = [], onChange, onGenerate = null } = $props()

  let draft = $state('')
  let dropdownOpen = $state(false)
  let items = $state([])
  let loading = $state(false)
  let activeIdx = $state(0)
  let inputEl = $state(null)
  let debounce = null

  function updateText(i, wert) {
    onChange(material.map((m, j) => (j === i ? { ...m, wert } : m)))
  }
  function removeAt(i) {
    onChange(material.filter((_, j) => j !== i))
  }
  function addText() {
    const v = draft.trim()
    if (!v) return
    onChange([...material, { typ: 'text', wert: v }])
    draft = ''
    closeDropdown()
  }
  function addNode(node) {
    onChange([...material, { typ: 'node', node_id: node.id, titel: node.title }])
    draft = ''
    closeDropdown()
    inputEl?.focus()
  }
  function closeDropdown() {
    dropdownOpen = false
    items = []
    activeIdx = 0
  }

  // "@" am Feldanfang triggert die Knotensuche.
  function onInput() {
    const m = draft.match(/^@(.*)$/)
    if (!m) {
      closeDropdown()
      return
    }
    const q = m[1].trim()
    clearTimeout(debounce)
    debounce = setTimeout(() => search(q), q ? 250 : 0)
  }

  async function search(q) {
    loading = true
    dropdownOpen = true
    try {
      const params = new URLSearchParams({ limit: '8' })
      if (q) params.set('q', q)
      const res = await fetch(`/api/context/nodes?${params}`, { credentials: 'include' })
      const raw = res.ok ? await res.json() : []
      const nodes = Array.isArray(raw) ? raw : (raw.items ?? [])
      items = nodes
      activeIdx = 0
    } catch {
      items = []
    } finally {
      loading = false
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
        addNode(items[activeIdx])
        return
      }
      if (e.key === 'Escape') {
        closeDropdown()
        return
      }
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      addText()
    }
  }
</script>

<div class="space-y-1">
  <!-- Vorhandene Einträge -->
  {#each material as mat, i}
    {#if mat.typ === 'node'}
      <span class="text-xs flex items-center gap-1">
        <span class="text-light-tx-2 dark:text-dark-tx-2" aria-hidden="true">📎</span>
        <a
          href="/knowledge/{mat.node_id}"
          class="text-light-bl dark:text-dark-bl hover:underline truncate max-w-[140px]"
          title={mat.titel || mat.node_id}
        >{mat.titel || mat.node_id}</a>
        <button
          onclick={() => removeAt(i)}
          class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re ml-auto"
          aria-label="Material entfernen"
        >✕</button>
      </span>
    {:else}
      <span class="flex items-center gap-1">
        <input
          type="text"
          value={mat.wert || ''}
          onchange={(e) => updateText(i, e.currentTarget.value)}
          placeholder="Material …"
          class="flex-1 min-w-0 bg-transparent text-xs text-light-tx dark:text-dark-tx
                 border-b border-transparent focus:border-primary dark:focus:border-primary-dark outline-none"
        />
        <button
          onclick={() => removeAt(i)}
          class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re"
          aria-label="Material entfernen"
        >✕</button>
      </span>
    {/if}
  {/each}

  <!-- Eingabefeld: Freitext + @-Knotensuche -->
  <div class="relative">
    <input
      bind:this={inputEl}
      bind:value={draft}
      oninput={onInput}
      onkeydown={onKeydown}
      onblur={() => setTimeout(closeDropdown, 200)}
      placeholder="+ Material (@ für Knoten)"
      class="w-full bg-transparent text-xs text-light-tx dark:text-dark-tx
             border-b border-light-ui-3 dark:border-dark-ui-3
             focus:border-primary dark:focus:border-primary-dark outline-none
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
        {:else if items.length === 0}
          <div class="px-3 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2">Kein Knoten gefunden</div>
        {:else}
          {#each items as node, i}
            <button
              onmousedown={(e) => { e.preventDefault(); addNode(node) }}
              class="w-full px-3 py-1.5 text-left text-xs flex items-start gap-2 transition-colors
                     {i === activeIdx ? 'bg-light-ui-2 dark:bg-dark-ui-2' : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
            >
              <span aria-hidden="true">📎</span>
              <span class="min-w-0 flex-1">
                <span class="block font-medium text-light-tx dark:text-dark-tx truncate">{node.title}</span>
                <span class="block text-light-tx-2 dark:text-dark-tx-2 truncate">
                  {CONTENT_TYPE_LABELS[node.content_type] ?? node.content_type}
                </span>
              </span>
            </button>
          {/each}
        {/if}
      </div>
    {/if}
  </div>

  <!-- Optionale Assistent-Erzeugung (klar getrennt) -->
  {#if onGenerate}
    <button
      onclick={onGenerate}
      class="text-xs text-light-tx-2 dark:text-dark-tx-2 opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity"
      title="Material vom Assistenten erzeugen lassen"
    >✦ erzeugen</button>
  {/if}
</div>
