<script>
  /**
   * Fachbegriffe der Stunde wählen (0.17, Päckchen A1, Schritt 3) — Mehrfachwahl.
   *
   * Suche wie `LinkedTermInput` (Tippen, Pfeiltasten, Enter, Escape), Liste wie
   * `MaterialCell`. Gesucht wird im Fach der Stunde **und seinen Bezugsfächern** — die löst
   * der Server auf (`mit_bezugsfaechern`); ein Treffer aus einem Bezugsfach trägt dessen
   * Namen.
   *
   * ⚠️ **Kein „+ anlegen".** Begriffe sind Fachschaftsgut: Eine Lehrkraft außerhalb der
   * Fachschaft dürfte nur privat anlegen, und einen privaten Begriff sähen die
   * Schüler:innen im Block „Aktueller Unterricht" nicht (Plan, Abschnitt 2). Fehlt einer,
   * sagt die Liste, wer ihn anlegt.
   *
   * begriffe: die Einträge mit `typ: 'concept'` aus `refs`
   * onAdd(eintrag), onRemove(nodeId): Die Leiste setzt `refs` daraus zusammen.
   */
  import { getContextNodes } from '$lib/api.js'
  import { subjectMap } from '$lib/stores/subjects.js'
  import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
  import { begriffAusTreffer, bezugsfach, ordneTreffer, suchparameter } from '$lib/begriffe_der_stunde.js'

  let { begriffe = [], subjectId = null, onAdd, onRemove } = $props()

  let draft = $state('')
  let dropdownOpen = $state(false)
  let items = $state([])
  let loading = $state(false)
  let activeIdx = $state(0)
  let debounce = null

  const gewaehlt = $derived(new Set(begriffe.map((b) => b.node_id)))
  const angeboten = $derived(items.filter((n) => !gewaehlt.has(n.id)))

  function closeDropdown() {
    dropdownOpen = false
    items = []
    activeIdx = 0
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
      const res = await getContextNodes(suchparameter(q, subjectId))
      items = ordneTreffer(Array.isArray(res) ? res : (res.items ?? []), q)
      activeIdx = 0
    } catch {
      items = []
    } finally {
      loading = false
    }
  }

  function pick(node) {
    onAdd(begriffAusTreffer(node))
    draft = ''
    closeDropdown()
  }

  function onKeydown(e) {
    if (!dropdownOpen || !angeboten.length) {
      if (e.key === 'Escape') closeDropdown()
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      activeIdx = Math.min(activeIdx + 1, angeboten.length - 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      activeIdx = Math.max(activeIdx - 1, 0)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      pick(angeboten[activeIdx])
    } else if (e.key === 'Escape') {
      closeDropdown()
    }
  }
</script>

<div class="space-y-1.5">
  {#if begriffe.length > 0}
    <div class="flex flex-wrap gap-1.5">
      {#each begriffe as b (b.node_id)}
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium
                     bg-light-pu/20 text-light-pu dark:bg-dark-pu/20 dark:text-dark-pu">
          <NodeTypeIcon category="concept" contentType={b.content_type ?? 'begriff'} size={12} />
          {b.titel ?? b.node_id}
          <button
            onclick={() => onRemove(b.node_id)}
            class="opacity-70 hover:opacity-100 ml-0.5"
            aria-label={`„${b.titel ?? b.node_id}“ entfernen`}
            title="Entfernen"
          >✕</button>
        </span>
      {/each}
    </div>
  {/if}

  <div class="relative">
    <input
      type="text"
      bind:value={draft}
      oninput={onInput}
      onkeydown={onKeydown}
      onblur={() => setTimeout(closeDropdown, 200)}
      placeholder="Begriff suchen …"
      class="w-full bg-transparent text-xs text-light-tx dark:text-dark-tx
             border-b border-light-ui-3 dark:border-dark-ui-3 focus:border-primary dark:focus:border-primary-dark outline-none
             placeholder:text-light-tx-2 dark:placeholder:text-dark-tx-2"
    />

    {#if dropdownOpen}
      <div
        class="absolute top-full left-0 right-0 mt-1 z-50 min-w-[220px]
               bg-light-bg dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3
               rounded-md shadow-xl max-h-64 overflow-y-auto"
      >
        {#if loading}
          <div class="px-3 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2">Suche…</div>
        {:else if angeboten.length === 0}
          <div class="px-3 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2">
            Kein passender Begriff. Fehlt einer, legt ihn die Fachschaft an.
          </div>
        {:else}
          {#each angeboten as node, i (node.id)}
            {@const fach = bezugsfach(node, subjectId, $subjectMap)}
            <button
              onmousedown={(e) => { e.preventDefault(); pick(node) }}
              class="w-full px-3 py-1.5 text-left text-xs flex items-center gap-2 transition-colors
                     {i === activeIdx ? 'bg-light-ui-2 dark:bg-dark-ui-2' : 'hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
            >
              <NodeTypeIcon category="concept" contentType={node.content_type} size={12} />
              <span class="truncate text-light-tx dark:text-dark-tx">{node.title}</span>
              {#if fach}
                <span class="ml-auto shrink-0 text-light-tx-2 dark:text-dark-tx-2">{fach}</span>
              {/if}
            </button>
          {/each}
        {/if}
      </div>
    {/if}
  </div>
</div>
