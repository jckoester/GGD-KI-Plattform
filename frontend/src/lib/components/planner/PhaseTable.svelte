<script>
  import { PRIO_COLORS } from '$lib/planner.js'
  import PhaseRow from './PhaseRow.svelte'

  /**
   * Props:
   * - phasen: array of phase objects
   * - verfuegbareMin: available minutes from slot (default 45)
   * - onChange(newPhasen)
   * - onSuggestCompetences(nodeId) — called when a node is linked (method/material)
   * - onMaterialCreate(phase, index) — called when ✦ is clicked on missing material
   */
  const {
    phasen = [],
    verfuegbareMin = 45,
    onChange,
    onSuggestCompetences = null,
    onMaterialCreate = null,
  } = $props()

  const gesamtMin = $derived((phasen || []).reduce((s, p) => s + (p.dauer_min || 0), 0))
  const ueberhang = $derived(gesamtMin - verfuegbareMin)

  // Kumulierte Minuten pro Phase
  const kumMinutes = $derived(
    (phasen || []).reduce((acc, p, i) => {
      acc.push(i === 0 ? 0 : acc[i - 1] + ((phasen[i - 1])?.dauer_min || 0))
      return acc
    }, [])
  )

  // Prio-Segmente für Zeitbudget-Balken
  const prioSegments = $derived(() => {
    const totals = { kern: 0, uebung: 0, vertiefung: 0 }
    for (const p of (phasen || [])) {
      totals[p.prio || 'kern'] = (totals[p.prio || 'kern'] || 0) + (p.dauer_min || 0)
    }
    return totals
  })

  function addPhase() {
    const newPhase = {
      id: crypto.randomUUID(),
      name: '',
      dauer_min: 15,
      beschreibung: null,
      prio: 'kern',
      methode: null,
      material: [],
    }
    onChange([...(phasen || []), newPhase])
  }

  function updatePhase(i, updated) {
    const next = [...phasen]
    next[i] = updated
    // Wenn ein node-Typ Method/Material verknüpft wird → Kompetenz-Sog
    if (onSuggestCompetences) {
      const m = updated.methode
      if (m?.typ === 'node' && m.node_id) onSuggestCompetences(m.node_id)
      for (const mat of (updated.material || [])) {
        if (mat?.typ === 'node' && mat.node_id) onSuggestCompetences(mat.node_id)
      }
    }
    onChange(next)
  }

  function deletePhase(i) {
    onChange(phasen.filter((_, j) => j !== i))
  }

  function movePhase(i, direction) {
    const next = [...phasen]
    const j = direction === 'up' ? i - 1 : i + 1
    if (j < 0 || j >= next.length) return
    ;[next[i], next[j]] = [next[j], next[i]]
    onChange(next)
  }

  function handleLinkMethod(phase) {
    // Öffnet Knoten-Suche in der Eltern-Seite — über Event oder Slot
    // Da wir kein Event-System haben, rufen wir onSuggestCompetences mit null auf
    // als Signal, dass der User einen Knoten-Link-Dialog braucht.
    // Die Eltern-Seite kann das ignorieren oder eine Suche öffnen.
  }

  function handleLinkMaterial(phase) {
    if (onMaterialCreate) onMaterialCreate(phase)
  }
</script>

<div class="space-y-2">
  <!-- Zeitbudget-Balken -->
  <div>
    <div class="flex items-baseline gap-2 mb-1">
      <span class="text-sm font-medium text-light-tx dark:text-dark-tx">
        {gesamtMin}′ geplant
      </span>
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
        / {verfuegbareMin}′ verfügbar
      </span>
      {#if ueberhang > 0}
        <span class="text-xs font-semibold text-light-re dark:text-dark-re">
          +{ueberhang}′ Überhang
        </span>
      {/if}
    </div>

    <div class="h-2.5 rounded-full overflow-hidden flex bg-light-ui-2 dark:bg-dark-ui-2 relative">
      {#if gesamtMin > 0}
        {@const ref = Math.max(gesamtMin, verfuegbareMin)}
        {#each ['kern', 'uebung', 'vertiefung'] as prio}
          {@const min = prioSegments()[prio] || 0}
          {#if min > 0}
            <div
              class="h-full transition-all"
              style="width: {(min / ref) * 100}%; background-color: {PRIO_COLORS[prio][0]}"
              title="{prio}: {min}′"
            ></div>
          {/if}
        {/each}
        {#if ueberhang > 0}
          <div
            class="h-full bg-light-re dark:bg-dark-re"
            style="width: {(ueberhang / (gesamtMin)) * 100}%"
            title="Überhang: {ueberhang}′"
          ></div>
        {/if}
      {/if}
      <!-- Soll-Markierung -->
      {#if gesamtMin > 0}
        {@const ref = Math.max(gesamtMin, verfuegbareMin)}
        <div
          class="absolute top-0 h-full w-0.5 bg-light-tx dark:bg-dark-tx opacity-40"
          style="left: {(verfuegbareMin / ref) * 100}%"
          title="{verfuegbareMin}′ verfügbar"
        ></div>
      {/if}
    </div>
  </div>

  <!-- Tabelle -->
  {#if phasen.length > 0}
    <div class="overflow-x-auto">
      <table class="w-full text-sm border-collapse">
        <thead>
          <tr class="border-b-2 border-light-ui-3 dark:border-dark-ui-3
                     text-xs font-semibold uppercase tracking-wide text-light-tx-2 dark:text-dark-tx-2">
            <th class="px-2 py-1.5 text-left w-20">Zeit</th>
            <th class="px-1 py-1.5 w-6"></th>
            <th class="px-2 py-1.5 text-left">Phase</th>
            <th class="px-2 py-1.5 text-right w-16">Min</th>
            <th class="px-2 py-1.5 text-left">Methode</th>
            <th class="px-2 py-1.5 text-left">Material</th>
            <th class="px-1 py-1.5 w-14"></th>
          </tr>
        </thead>
        <tbody>
          {#each phasen as phase, i (phase.id ?? i)}
            <PhaseRow
              {phase}
              kumMin={kumMinutes[i]}
              canMoveUp={i > 0}
              canMoveDown={i < phasen.length - 1}
              onChange={(updated) => updatePhase(i, updated)}
              onDelete={() => deletePhase(i)}
              onMove={(dir) => movePhase(i, dir)}
              onLinkMethod={handleLinkMethod}
              onLinkMaterial={() => handleLinkMaterial(phase)}
            />
          {/each}
        </tbody>
      </table>
    </div>
  {:else}
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 italic py-2">
      Noch keine Phasen — erste Phase hinzufügen.
    </p>
  {/if}

  <!-- Neue Phase -->
  <button
    onclick={addPhase}
    class="text-sm text-light-bl dark:text-dark-bl hover:opacity-80 font-medium"
  >
    + Phase hinzufügen
  </button>
</div>
