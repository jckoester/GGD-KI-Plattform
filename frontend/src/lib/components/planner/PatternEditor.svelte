<script>
  import { setWeekPattern, generateSlots } from '$lib/api.js'

  const { open = false, groupId, patterns = [], schuljahr = '', onSaved, onGenerated, onClose } = $props()

  const WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr']
  const PERIODS = [1, 2, 3, 4, 5, 6, 7, 8]

  let halbjahr = $state(1)
  let rows = $state([])
  let saving = $state(false)
  let generating = $state(false)
  let error = $state(null)
  let genSuccess = $state(null)

  // Lokalen State mit aktuellen Mustern für gewähltes Halbjahr befüllen
  $effect(() => {
    if (open) {
      syncRows()
      error = null
      genSuccess = null
    }
  })

  $effect(() => {
    syncRows()
  })

  function syncRows() {
    rows = patterns
      .filter(p => p.halbjahr === halbjahr)
      .map(p => ({ weekday: p.weekday, start_period: p.start_period, periods: p.periods }))
  }

  function addRow() {
    rows = [...rows, { weekday: 0, start_period: 1, periods: 1 }]
  }

  function removeRow(i) {
    rows = rows.filter((_, idx) => idx !== i)
  }

  function updateRow(i, key, value) {
    rows = rows.map((r, idx) => idx === i ? { ...r, [key]: Number(value) } : r)
  }

  async function save() {
    saving = true
    error = null
    try {
      const updated = await setWeekPattern(groupId, halbjahr, rows)
      onSaved(halbjahr, updated)
    } catch (e) {
      error = e.message
    } finally {
      saving = false
    }
  }

  async function generate(regenerate = false) {
    generating = true
    error = null
    genSuccess = null
    try {
      const stats = await generateSlots(groupId, halbjahr, regenerate)
      genSuccess = `${stats.created} Slots für HJ ${halbjahr} generiert.`
      if (stats.used_hj1_fallback) genSuccess += ' (HJ-1-Muster als Fallback verwendet)'
      onGenerated(stats)
    } catch (e) {
      error = e.message
    } finally {
      generating = false
    }
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 bg-black/40 flex items-center justify-center"
    onclick={(e) => { if (e.target === e.currentTarget) onClose() }}
  >
    <div class="bg-light-bg dark:bg-dark-bg border border-light-ui-3 dark:border-dark-ui-3 rounded-xl shadow-2xl w-full max-w-lg p-6">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-base font-semibold text-light-tx dark:text-dark-tx">Wochenmuster bearbeiten</h2>
        <button
          onclick={onClose}
          class="p-1.5 rounded hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2 transition-colors"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- Halbjahr-Auswahl -->
      <div class="flex gap-1 mb-4">
        {#each [1, 2] as hj}
          <button
            onclick={() => { halbjahr = hj }}
            class="px-4 py-1.5 rounded-md text-sm font-medium transition-colors
                   {halbjahr === hj
                     ? 'bg-primary dark:bg-primary-dark text-white'
                     : 'bg-light-bg-2 dark:bg-dark-bg-2 text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
          >
            {hj}. Halbjahr
          </button>
        {/each}
      </div>

      <!-- Muster-Zeilen -->
      <div class="mb-3">
        {#if rows.length === 0}
          <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 italic py-2">
            Keine Einträge — bitte "+ Zeile" klicken.
          </p>
        {:else}
          <div class="space-y-2">
            {#each rows as row, i}
              <div class="flex items-center gap-2">
                <select
                  value={row.weekday}
                  onchange={(e) => updateRow(i, 'weekday', e.currentTarget.value)}
                  class="px-2 py-1 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                         text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                >
                  {#each WEEKDAYS as d, j}
                    <option value={j}>{d}</option>
                  {/each}
                </select>

                <select
                  value={row.start_period}
                  onchange={(e) => updateRow(i, 'start_period', e.currentTarget.value)}
                  class="px-2 py-1 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                         text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                >
                  {#each PERIODS as p}
                    <option value={p}>{p}. Stunde</option>
                  {/each}
                </select>

                <select
                  value={row.periods}
                  onchange={(e) => updateRow(i, 'periods', e.currentTarget.value)}
                  class="px-2 py-1 text-sm bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-3 dark:border-dark-ui-3 rounded-md
                         text-light-tx dark:text-dark-tx outline-none focus:border-primary dark:focus:border-primary-dark"
                >
                  <option value={1}>Einzelstunde</option>
                  <option value={2}>Doppelstunde</option>
                </select>

                <button
                  onclick={() => removeRow(i)}
                  class="p-1 rounded hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 text-light-tx-2 dark:text-dark-tx-2 hover:text-light-re dark:hover:text-dark-re transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                       fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                </button>
              </div>
            {/each}
          </div>
        {/if}
        <button
          onclick={addRow}
          class="mt-2 text-sm text-light-bl dark:text-dark-bl hover:opacity-80 transition-opacity"
        >+ Zeile</button>
      </div>

      {#if error}
        <p class="text-sm text-light-re dark:text-dark-re mb-3">{error}</p>
      {/if}
      {#if genSuccess}
        <p class="text-sm text-green-600 dark:text-green-400 mb-3">{genSuccess}</p>
      {/if}

      <!-- Aktionen -->
      <div class="flex items-center justify-between pt-4 border-t border-light-ui-3 dark:border-dark-ui-3">
        <div class="flex gap-2">
          <button
            onclick={() => generate(false)}
            disabled={generating || saving}
            class="px-3 py-1.5 text-sm rounded-lg font-medium border border-light-ui-3 dark:border-dark-ui-3
                   text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Generieren HJ{halbjahr}
          </button>
          <button
            onclick={() => generate(true)}
            disabled={generating || saving}
            class="px-3 py-1.5 text-sm rounded-lg font-medium border border-light-ui-3 dark:border-dark-ui-3
                   text-light-tx dark:text-dark-tx hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors
                   disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Neu generieren
          </button>
        </div>
        <div class="flex gap-2">
          <button
            onclick={onClose}
            class="px-4 py-2 text-sm rounded-lg text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-bg-2 dark:hover:bg-dark-bg-2 transition-colors"
          >Schließen</button>
          <button
            onclick={save}
            disabled={saving || generating}
            class="px-4 py-2 text-sm rounded-lg font-medium bg-primary dark:bg-primary-dark text-white
                   hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? 'Speichern…' : 'Muster speichern'}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
