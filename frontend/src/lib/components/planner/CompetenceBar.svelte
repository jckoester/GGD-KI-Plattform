<script>
  import IKSelector from '$lib/components/IKSelector.svelte'
  import PKSelector from '$lib/components/PKSelector.svelte'
  import NodeTypeIcon from '$lib/components/NodeTypeIcon.svelte'
  import BegriffSelector from './BegriffSelector.svelte'
  import { aufteilen, mitBegriff, ohneBegriff } from '$lib/begriffe_der_stunde.js'

  /**
   * Kompetenzen und Fachbegriffe der Stunde — beide in `refs`, getrennt angezeigt und
   * bearbeitet (Begriffe seit 0.17).
   *
   * Props:
   * - refs: array of {node_id, typ, code, titel, partiell, content_type?}
   * - subjectId: for selectors
   * - readonly: boolean
   * - onChange(newRefs)
   *
   * Die Vorschlags-Chips (`suggestions`) sind 0.17 entfallen: Die Seite füllte sie nie.
   * Vorschläge aus verknüpftem Material bekommt der Stundenassistent (`suggested_refs`).
   */
  const {
    refs = [],
    subjectId = null,
    grade = null,
    readonly = false,
    onChange = () => {},
  } = $props()

  let editing = $state(false)

  const getrennt = $derived(aufteilen(refs))

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

  const chipBase = 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium'
  function chipColor(typ) {
    // Semantische Tokens (kein rohes Palettengrün/-blau/-lila) — Muster wie HinweisChip:
    // /20-Tönung als Hintergrund, volle Farbe als Text.
    if (typ === 'ik') return 'bg-light-bl/20 text-light-bl dark:bg-dark-bl/20 dark:text-dark-bl'
    if (typ === 'pk') return 'bg-light-gr/20 text-light-gr dark:bg-dark-gr/20 dark:text-dark-gr'
    return 'bg-light-pu/20 text-light-pu dark:bg-dark-pu/20 dark:text-dark-pu'
  }
</script>

<div class="space-y-2">
  <!-- Chips: Kompetenzen -->
  <div class="flex flex-wrap gap-1.5 items-center min-h-[26px]">
    {#each getrennt.kompetenzen as ref (ref.node_id)}
      <span class="{chipBase} {chipColor(ref.typ)}" title={ref.titel ?? ref.code ?? ''}>
        {ref.code ?? ref.titel ?? ref.node_id}
        {#if ref.partiell}<span class="opacity-60">[…]</span>{/if}
      </span>
    {/each}

    {#if refs.length === 0 && !editing}
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 italic">Keine Kompetenzen oder Begriffe</span>
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

  <!-- Chips: Begriffe — mit Symbol, damit Fachbegriff und Stoffsteckbrief zu unterscheiden sind -->
  {#if getrennt.begriffe.length > 0}
    <div class="flex flex-wrap gap-1.5 items-center">
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">Begriffe:</span>
      {#each getrennt.begriffe as ref (ref.node_id)}
        <span class="{chipBase} {chipColor(ref.typ)}" title={ref.titel ?? ''}>
          <NodeTypeIcon category="concept" contentType={ref.content_type ?? 'begriff'} size={12} />
          {ref.titel ?? ref.node_id}
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
          {grade}
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
          {grade}
          selected={pkSelected}
          onchange={onPkChange}
        />
      </div>
      <div>
        <div class="text-xs font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-1">
          Fachbegriffe
        </div>
        <BegriffSelector
          begriffe={getrennt.begriffe}
          {subjectId}
          onAdd={(eintrag) => onChange(mitBegriff(refs, eintrag))}
          onRemove={(nodeId) => onChange(ohneBegriff(refs, nodeId))}
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
