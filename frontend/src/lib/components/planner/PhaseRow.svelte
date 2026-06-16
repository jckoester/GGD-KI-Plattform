<script>
  import { PRIO_COLORS, PRIO_LABELS } from '$lib/planner.js'
  import MaterialCell from './MaterialCell.svelte'

  /**
   * Props:
   * - phase: {id, name, dauer_min, beschreibung, prio, methode, material}
   * - kumMin: cumulative minutes before this phase
   * - canMoveUp / canMoveDown
   * - onChange(updatedPhase)
   * - onDelete()
   * - onMove(direction: 'up'|'down')
   * - onLinkMethod(phase) — opens node-search for method
   * - onLinkMaterial(phase) — opens node-search for material
   */
  const {
    phase,
    kumMin = 0,
    canMoveUp = false,
    canMoveDown = false,
    onChange,
    onDelete,
    onMove,
    onLinkMethod = null,
    onLinkMaterial = null,
    reviewMode = false,
    reviewPhaseStatus = 'erledigt',
    onReviewStatusChange = null,
  } = $props()

  const PRIOS = ['kern', 'uebung', 'vertiefung']
  const endMin = $derived(kumMin + (phase.dauer_min || 0))

  function patch(updates) {
    onChange({ ...phase, ...updates })
  }

  function methodDisplay(m) {
    if (!m) return ''
    return m.typ === 'node' ? (m.titel || '') : (m.wert || '')
  }

  let editDesc = $state(false)
  let prioOpen = $state(false)
  let menuOpen = $state(false)

  const prioColor = $derived(PRIO_COLORS[phase.prio] ?? PRIO_COLORS.kern)
</script>

<tr class="border-b border-light-ui-3 dark:border-dark-ui-3 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 group">
  <!-- Zeit -->
  <td class="px-2 py-2 text-xs text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap w-20">
    {kumMin}–{endMin}′
  </td>

  <!-- Prio-Pill + Select -->
  <td class="px-2 py-2 w-24 align-top">
    <div class="relative inline-block">
      <button
        title="Priorität ändern"
        onclick={() => { prioOpen = !prioOpen }}
        class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
               text-white whitespace-nowrap hover:opacity-90 transition-opacity"
        style="background-color: {prioColor[0]}"
        aria-label="Priorität: {PRIO_LABELS[phase.prio]}"
      >{PRIO_LABELS[phase.prio]}</button>
      {#if prioOpen}
        <div
          role="none"
          class="absolute left-0 top-full mt-1 z-50 bg-light-bg dark:bg-dark-bg
                 border border-light-ui-3 dark:border-dark-ui-3 rounded-lg shadow-xl py-1 w-32"
          onclick={(e) => e.stopPropagation()}
        >
          {#each PRIOS as p}
            <button
              onclick={() => { patch({ prio: p }); prioOpen = false }}
              class="w-full flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-light-bg-2 dark:hover:bg-dark-bg-2
                     {phase.prio === p ? 'font-semibold text-light-tx dark:text-dark-tx' : 'text-light-tx-2 dark:text-dark-tx-2'}"
            >
              <span class="w-2.5 h-2.5 rounded-sm inline-block" style="background-color: {PRIO_COLORS[p][0]}"></span>
              {PRIO_LABELS[p]}
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </td>

  <!-- Phase-Name + Beschreibung -->
  <td class="px-2 py-2 min-w-[160px]">
    <input
      type="text"
      value={phase.name}
      onchange={(e) => patch({ name: e.currentTarget.value })}
      placeholder="Phasen-Name"
      class="w-full bg-transparent text-sm font-medium text-light-tx dark:text-dark-tx
             border-b border-transparent focus:border-primary dark:focus:border-primary-dark outline-none"
    />
    {#if editDesc || phase.beschreibung}
      <textarea
        rows="2"
        value={phase.beschreibung || ''}
        onchange={(e) => patch({ beschreibung: e.currentTarget.value || null })}
        placeholder="Beschreibung …"
        class="mt-1 w-full text-xs bg-transparent text-light-tx-2 dark:text-dark-tx-2
               border border-transparent focus:border-light-ui-3 dark:focus:border-dark-ui-3
               rounded px-1 resize-none outline-none"
      ></textarea>
    {:else}
      <button
        onclick={() => { editDesc = true }}
        class="text-xs text-light-tx-2 dark:text-dark-tx-2 opacity-0 group-hover:opacity-60 hover:!opacity-100 mt-0.5"
      >+ Beschreibung</button>
    {/if}
  </td>

  <!-- Dauer -->
  <td class="px-2 py-2 w-20 align-top">
    <input
      type="number"
      min="1"
      max="480"
      value={phase.dauer_min}
      onchange={(e) => patch({ dauer_min: Math.max(1, parseInt(e.currentTarget.value) || 1) })}
      class="w-full bg-transparent text-sm text-light-tx dark:text-dark-tx text-right
             border-b border-transparent focus:border-primary dark:focus:border-primary-dark outline-none"
      aria-label="Dauer in Minuten"
    />
  </td>

  <!-- Methode -->
  <td class="px-2 py-2 min-w-[120px]">
    {#if phase.methode?.typ === 'node'}
      <span class="text-xs flex items-center gap-1">
        <span class="text-primary dark:text-primary-dark">⬡</span>
        <span class="text-light-tx dark:text-dark-tx">{methodDisplay(phase.methode)}</span>
        <button
          onclick={() => patch({ methode: null })}
          class="text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re ml-1"
          aria-label="Methode entfernen"
        >✕</button>
      </span>
    {:else}
      <input
        type="text"
        value={phase.methode?.wert || ''}
        onchange={(e) => {
          const v = e.currentTarget.value.trim()
          patch({ methode: v ? { typ: 'text', wert: v } : null })
        }}
        placeholder="Methode …"
        class="w-full bg-transparent text-xs text-light-tx dark:text-dark-tx
               border-b border-transparent focus:border-primary dark:focus:border-primary-dark outline-none"
      />
    {/if}
    {#if onLinkMethod}
      <button
        onclick={() => onLinkMethod(phase)}
        class="text-xs text-light-tx-2 dark:text-dark-tx-2 opacity-0 group-hover:opacity-60 hover:!opacity-100"
        title="Methoden-Knoten verknüpfen"
      >⬡ Knoten</button>
    {/if}
  </td>

  <!-- Material -->
  <td class="px-2 py-2 min-w-[140px] align-top">
    <MaterialCell
      material={phase.material || []}
      onChange={(m) => patch({ material: m })}
      onGenerate={onLinkMaterial ? () => onLinkMaterial(phase) : null}
    />
  </td>

  <!-- Aktionen / Review-Status -->
  <td class="px-1 py-2 w-14">
    {#if reviewMode}
      <div class="flex flex-col gap-0.5 items-end">
        <button
          onclick={() => onReviewStatusChange?.('erledigt')}
          class="px-1.5 py-0.5 rounded text-xs font-medium transition-colors
                 {reviewPhaseStatus === 'erledigt'
                   ? 'bg-green-100 text-green-700 dark:bg-green-950/40 dark:text-green-300'
                   : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
          title="Erledigt"
          aria-pressed={reviewPhaseStatus === 'erledigt'}
        >✓</button>
        <button
          onclick={() => onReviewStatusChange?.('offen')}
          class="px-1.5 py-0.5 rounded text-xs font-medium transition-colors
                 {reviewPhaseStatus === 'offen'
                   ? 'bg-orange-100 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300'
                   : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
          title="Offen (verschoben)"
          aria-pressed={reviewPhaseStatus === 'offen'}
        >⏸</button>
        <button
          onclick={() => onReviewStatusChange?.('gestrichen')}
          class="px-1.5 py-0.5 rounded text-xs font-medium transition-colors
                 {reviewPhaseStatus === 'gestrichen'
                   ? 'bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-300'
                   : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
          title="Gestrichen"
          aria-pressed={reviewPhaseStatus === 'gestrichen'}
        >✕</button>
      </div>
    {:else}
      <div class="flex flex-col gap-0.5 items-end">
        <button
          onclick={() => onMove('up')}
          disabled={!canMoveUp}
          class="p-0.5 rounded text-light-tx-2 dark:text-dark-tx-2 disabled:opacity-20
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
          aria-label="Phase nach oben"
        >↑</button>
        <button
          onclick={() => onMove('down')}
          disabled={!canMoveDown}
          class="p-0.5 rounded text-light-tx-2 dark:text-dark-tx-2 disabled:opacity-20
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
          aria-label="Phase nach unten"
        >↓</button>
        <button
          onclick={onDelete}
          class="p-0.5 rounded text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2"
          aria-label="Phase löschen"
        >✕</button>
      </div>
    {/if}
  </td>
</tr>
