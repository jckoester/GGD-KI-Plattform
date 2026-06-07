<script>
  import { getContextNodes, updateContextNode, deleteContextNode } from '$lib/api.js'
  import { CONTENT_TYPES, CATEGORY_LABELS, SCOPE_ANCHOR_CONTENT_TYPES } from '$lib/taxonomy.js'
  import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'

  let nodes = $state([])
  let loading = $state(false)
  let error = $state(null)

  // Filter
  let schuljahr = $state('')
  let selectedCategory = $state('')
  let q = $state('')
  let searchTimer = null

  // Löschen-Bestätigung
  let confirmDeleteId = $state(null)
  let deleteLoading = $state(false)

  async function load() {
    loading = true
    error = null
    try {
      const params = { status: 'archived', owner: 'me' }
      if (q.trim().length >= 2) params.q = q.trim()
      if (selectedCategory) params.category = selectedCategory
      nodes = await getContextNodes(params)
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  $effect(() => { selectedCategory; load() })

  function onSearchInput(e) {
    q = e.target.value
    clearTimeout(searchTimer)
    searchTimer = setTimeout(load, 300)
  }

  // Schuljahr-Filter clientseitig
  const filteredNodes = $derived(
    schuljahr
      ? nodes.filter(n => n.schuljahr === schuljahr)
      : nodes
  )

  // Schuljahre aus den geladenen Knoten ableiten
  const availableSchuljahre = $derived(
    [...new Set(nodes.map(n => n.schuljahr).filter(Boolean))].sort().reverse()
  )

  async function restore(node) {
    await updateContextNode(node.id, { status: 'active' })
    nodes = nodes.filter(n => n.id !== node.id)
  }

  async function confirmDelete(nodeId) {
    deleteLoading = true
    try {
      await deleteContextNode(nodeId)
      nodes = nodes.filter(n => n.id !== nodeId)
      confirmDeleteId = null
    } catch (e) {
      error = e.message
    } finally {
      deleteLoading = false
    }
  }
</script>

<div class="h-full overflow-y-auto p-6 max-w-4xl">
  <div class="flex items-center justify-between mb-6">
    <div>
      <a href="/knowledge"
         class="text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx
                transition-colors mb-1 block">
        ← Wissensgraph
      </a>
      <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">Archiv</h1>
    </div>
  </div>

  <!-- Filterleiste -->
  <div class="flex flex-wrap gap-2 mb-4">
    <input
      type="search"
      placeholder="Titel suchen…"
      value={q}
      oninput={onSearchInput}
      class="flex-1 min-w-48 px-3 py-1.5 text-sm rounded-md border
             border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg
             text-light-tx dark:text-dark-tx focus:outline-none focus:border-primary dark:focus:border-primary-dark"
    />

    <!-- Schuljahr-Filter -->
    <select
      bind:value={schuljahr}
      class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
             bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
    >
      <option value="">Alle Schuljahre</option>
      {#each availableSchuljahre as sj}
        <option value={sj}>{sj}</option>
      {/each}
    </select>

    <!-- Kategorie-Filter -->
    <select
      bind:value={selectedCategory}
      class="px-3 py-1.5 text-sm rounded-md border border-light-ui-3 dark:border-dark-ui-3
             bg-light-bg dark:bg-dark-bg text-light-tx dark:text-dark-tx"
    >
      <option value="">Alle Typen</option>
      {#each Object.keys(CONTENT_TYPES) as cat}
        <option value={cat}>{CATEGORY_LABELS[cat]}</option>
      {/each}
    </select>
  </div>

  <!-- Tabelle -->
  {#if loading}
    <div class="py-8 text-center text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen…</div>
  {:else if error}
    <div class="py-4 text-sm text-light-re dark:text-dark-re">{error}</div>
  {:else if filteredNodes.length === 0}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 py-8 text-center">
      Keine archivierten Knoten{schuljahr ? ` aus ${schuljahr}` : ''}.
    </p>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-sm">
        <thead>
          <tr class="border-b border-light-ui-3 dark:border-dark-ui-3">
            <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2">Titel</th>
            <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2">Typ</th>
            <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2">Schuljahr</th>
            <th class="px-3 py-2 font-medium text-light-tx-2 dark:text-dark-tx-2">Archiviert</th>
            <th class="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {#each filteredNodes as node (node.id)}
            <tr class="border-b border-light-ui-3 dark:border-dark-ui-3
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors">
              <td class="px-3 py-2">
                <a href="/knowledge/{node.id}"
                   class="text-light-tx dark:text-dark-tx font-medium hover:underline flex items-center gap-2">
                  <NodeTypeIcon category={node.category} contentType={node.content_type} size={16} />
                  {#if SCOPE_ANCHOR_CONTENT_TYPES.has(node.content_type)}
                    <span title="Einstiegsknoten" class="opacity-60">⚓</span>
                  {/if}
                  {node.title}
                </a>
              </td>
              <td class="px-3 py-2 text-light-tx-2 dark:text-dark-tx-2 text-xs">
                {CATEGORY_LABELS[node.category] ?? node.category}
                {#if node.content_type}<span class="opacity-60"> / {node.content_type}</span>{/if}
              </td>
              <td class="px-3 py-2 text-light-tx-2 dark:text-dark-tx-2 text-xs">
                {node.schuljahr ?? '—'}
              </td>
              <td class="px-3 py-2 text-light-tx-3 dark:text-dark-tx-3 text-xs whitespace-nowrap">
                {node.archived_at
                  ? new Date(node.archived_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
                  : '—'}
              </td>
              <td class="px-3 py-2" onclick={e => e.stopPropagation()}>
                <div class="flex gap-2 items-center">
                  <button
                    onclick={() => restore(node)}
                    class="text-xs text-primary dark:text-dark-bl
                           hover:underline transition-colors"
                  >
                    Wiederherstellen
                  </button>

                  {#if confirmDeleteId === node.id}
                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Sicher?</span>
                    <button
                      onclick={() => confirmDelete(node.id)}
                      disabled={deleteLoading}
                      class="text-xs text-light-re dark:text-dark-re hover:underline disabled:opacity-50"
                    >
                      Ja, löschen
                    </button>
                    <button
                      onclick={() => { confirmDeleteId = null }}
                      class="text-xs text-light-tx-2 dark:text-dark-tx-2 hover:underline"
                    >
                      Abbrechen
                    </button>
                  {:else}
                    <button
                      onclick={() => { confirmDeleteId = node.id }}
                      class="text-xs text-light-tx-3 dark:text-dark-tx-3
                             hover:text-light-re dark:hover:text-dark-re transition-colors"
                    >
                      Löschen
                    </button>
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
