<script>
  import { getContextNodes, deleteContextNode, reactivateContextNode } from '$lib/api.js'
  import { CONTENT_TYPES, CATEGORY_LABELS, SCOPE_ANCHOR_CONTENT_TYPES } from '$lib/taxonomy.js'
  import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
  import ErrorBanner from '$lib/components/ErrorBanner.svelte'
  import SuccessBanner from '$lib/components/SuccessBanner.svelte'

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
  // Referenzen aus einer 409-Antwort: Wer verweist noch auf den Baustein?
  let blockiertVon = $state(null)
  let hinweis = $state(null)

  const heute = new Date().toISOString().slice(0, 10)

  /** Wurde der Baustein automatisch archiviert, weil sein Datum verstrichen ist? */
  function abgelaufenAm(node) {
    return node.valid_until && node.valid_until < heute ? node.valid_until : null
  }

  function alsDatum(iso) {
    return new Date(iso).toLocaleDateString('de-DE', {
      day: '2-digit', month: '2-digit', year: 'numeric',
    })
  }

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
    error = null
    hinweis = null
    try {
      // Nicht bloß den Status setzen: Ein abgelaufener Baustein trüge sonst weiter sein
      // altes Datum und wäre in derselben Nacht wieder archiviert. Das neue Datum
      // bestimmt der Server aus der Bausteinart.
      const zurueck = await reactivateContextNode(node.id)
      nodes = nodes.filter(n => n.id !== node.id)
      hinweis = zurueck.valid_until
        ? `„${zurueck.title}" ist wieder aktiv — gültig bis ${alsDatum(zurueck.valid_until)}.`
        : `„${zurueck.title}" ist wieder aktiv und läuft nicht ab.`
    } catch (e) {
      error = e.message
    }
  }

  async function confirmDelete(nodeId) {
    deleteLoading = true
    error = null
    blockiertVon = null
    try {
      await deleteContextNode(nodeId)
      nodes = nodes.filter(n => n.id !== nodeId)
      confirmDeleteId = null
    } catch (e) {
      if (e.status === 409 && e.detail?.referenzen) {
        // Andere bauen auf diesem Baustein auf — Löschen bricht ihre Verweise.
        blockiertVon = { nodeId, referenzen: e.detail.referenzen, nachricht: e.message }
        confirmDeleteId = null
      } else {
        error = e.message
      }
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

  {#if hinweis}
    <div class="mb-4"><SuccessBanner message={hinweis} /></div>
  {/if}

  {#if blockiertVon}
    <div class="mb-4 p-3 rounded-md border border-light-ui-3 dark:border-dark-ui-3
                bg-light-bg-2 dark:bg-dark-bg-2 text-sm">
      <p class="text-light-tx dark:text-dark-tx mb-2">{blockiertVon.nachricht}</p>
      <ul class="mb-2 space-y-0.5 text-light-tx-2 dark:text-dark-tx-2">
        {#each blockiertVon.referenzen as ref}
          <li>
            <a href="/knowledge/{ref.id}" class="hover:underline">{ref.title}</a>
            <span class="opacity-60 text-xs"> — {ref.relation}</span>
          </li>
        {/each}
      </ul>
      <p class="text-light-tx-2 dark:text-dark-tx-2 text-xs">
        Der Baustein bleibt archiviert: Er ist damit aus Suche und Assistenten heraus,
        die Verweise bleiben aber heil.
      </p>
      <button
        onclick={() => { blockiertVon = null }}
        class="mt-2 text-xs text-light-bl dark:text-dark-bl hover:underline"
      >
        Verstanden
      </button>
    </div>
  {/if}

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
    <ErrorBanner message={error} />
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
                {node.archived_at ? alsDatum(node.archived_at) : '—'}
                {#if abgelaufenAm(node)}
                  <span class="block text-light-tx-2 dark:text-dark-tx-2">
                    abgelaufen am {alsDatum(abgelaufenAm(node))}
                  </span>
                {/if}
              </td>
              <td class="px-3 py-2" onclick={e => e.stopPropagation()}>
                <div class="flex gap-2 items-center">
                  <button
                    onclick={() => restore(node)}
                    title={abgelaufenAm(node)
                      ? 'Holt den Baustein zurück und setzt ein neues Ablaufdatum'
                      : 'Holt den Baustein zurück'}
                    class="text-xs text-light-bl dark:text-dark-bl
                           hover:underline transition-colors"
                  >
                    {abgelaufenAm(node) ? 'Reaktivieren' : 'Wiederherstellen'}
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
