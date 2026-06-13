<script>
  import IKSelector from '$lib/components/IKSelector.svelte'
  import PKSelector from '$lib/components/PKSelector.svelte'

  /**
   * Props:
   * - refs: array of {node_id, typ, code, titel, partiell}
   * - suggestions: array of {node_id, typ, code, titel, partiell, quelle}
   * - subjectId: for selectors
   * - readonly: boolean
   * - onChange(newRefs)
   * - onDismissSuggestion(nodeId)
   */
  const {
    refs = [],
    suggestions = [],
    subjectId = null,
    readonly = false,
    onChange = () => {},
    onDismissSuggestion = () => {},
  } = $props()

  let editing = $state(false)

  // IKSelector / PKSelector erwarten jeweils ihr eigenes Format
  let ikSelected = $derived(
    refs.filter(r => r.typ === 'ik').map(r => ({
      node_id: r.node_id,
      title: r.titel ?? r.code ?? '',
      nr: r.code ?? '',
      partiell: r.partiell ?? false,
    }))
  )
  let pkSelected = $derived(
    refs.filter(r => r.typ === 'pk').map(r => ({
      node_id: r.node_id,
      title: r.titel ?? r.code ?? '',
      pk_id: r.code ?? '',
    }))
  )

  function onIkChange(newIks) {
    const filtered = refs.filter(r => r.typ !== 'ik')
    const added = newIks.map(ik => ({
      node_id: ik.node_id,
      typ: 'ik',
      code: ik.nr,
      titel: ik.title,
      partiell: ik.partiell ?? false,
    }))
    onChange([...filtered, ...added])
  }

  function onPkChange(newPks) {
    const filtered = refs.filter(r => r.typ !== 'pk')
    const added = newPks.map(pk => ({
      node_id: pk.node_id,
      typ: 'pk',
      code: pk.pk_id,
      titel: pk.title,
      partiell: false,
    }))
    onChange([...filtered, ...added])
  }

  function acceptSuggestion(s) {
    if (refs.some(r => r.node_id === s.node_id)) return
    onChange([...refs, { node_id: s.node_id, typ: s.typ, code: s.code, titel: s.titel, partiell: false }])
  }

  const chipBase = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium'
  function chipColor(typ) {
    if (typ === 'ik') return 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200'
    if (typ === 'pk') return 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200'
    return 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200'
  }
</script>

<div class="space-y-2">
  <!-- Chips -->
  <div class="flex flex-wrap gap-1.5 items-center min-h-[26px]">
    {#each refs as ref (ref.node_id)}
      <span class="{chipBase} {chipColor(ref.typ)}" title={ref.titel ?? ref.code ?? ''}>
        {ref.code ?? ref.titel ?? ref.node_id}
        {#if ref.partiell}<span class="opacity-60">[…]</span>{/if}
      </span>
    {/each}

    {#if refs.length === 0 && !editing}
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 italic">Keine Kompetenzen</span>
    {/if}

    {#if !readonly && !editing}
      <button
        onclick={() => { editing = true }}
        class="text-xs text-light-tx-2 dark:text-dark-tx-2 hover:text-light-bl dark:hover:text-dark-bl
               border border-light-ui-3 dark:border-dark-ui-3 rounded px-2 py-0.5"
      >
        ✎ bearbeiten
      </button>
    {/if}
  </div>

  <!-- Vorschlags-Chips -->
  {#if suggestions.length > 0}
    <div class="flex flex-wrap gap-1.5 items-center">
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Vorschläge:</span>
      {#each suggestions as s (s.node_id)}
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs
                     border border-dashed {chipColor(s.typ)} opacity-75">
          + {s.code ?? s.titel ?? s.node_id}
          <button
            onclick={() => acceptSuggestion(s)}
            title="Übernehmen"
            class="hover:opacity-100 opacity-70 font-bold ml-0.5"
          >✓</button>
          <button
            onclick={() => onDismissSuggestion(s.node_id)}
            title="Verwerfen"
            class="hover:opacity-100 opacity-70 ml-0.5"
          >✕</button>
        </span>
      {/each}
    </div>
  {/if}

  <!-- Editor -->
  {#if editing}
    <div class="border border-light-ui-3 dark:border-dark-ui-3 rounded-lg p-3 space-y-3 bg-light-bg-2 dark:bg-dark-bg-2">
      <div>
        <div class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">
          Inhaltliche Kompetenzen (IK)
        </div>
        <IKSelector
          {subjectId}
          selected={ikSelected}
          onchange={onIkChange}
        />
      </div>
      <div>
        <div class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">
          Prozessbezogene Kompetenzen (PK)
        </div>
        <PKSelector
          {subjectId}
          selected={pkSelected}
          onchange={onPkChange}
        />
      </div>
      <div class="flex justify-end">
        <button
          onclick={() => { editing = false }}
          class="text-xs text-light-bl dark:text-dark-bl hover:opacity-80 font-medium"
        >
          Fertig
        </button>
      </div>
    </div>
  {/if}
</div>
