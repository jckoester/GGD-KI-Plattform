<script>
  import { onMount } from 'svelte'
  import { getHeatmap } from '$lib/api.js'
  import { ArrowLeft, ChartColumn, LoaderCircle, CircleX } from 'lucide-svelte'

  const DAY_NAMES = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

  let data    = $state(null)
  let loading = $state(true)
  let error   = $state(null)

  function formatWeek(start, end) {
    const fmt = (s) => {
      const [, m, d] = s.split('-')
      return `${d}.${m}.`
    }
    const [y] = end.split('-')
    return `${fmt(start)} – ${fmt(end)}${y}`
  }

  onMount(async () => {
    try {
      data = await getHeatmap()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  })
</script>

<svelte:head>
  <title>Anzahl Prompts</title>
</svelte:head>

<button
  onclick={() => history.back()}
  class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
  <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="max-w-5xl mx-auto py-8 space-y-6">

  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2 text-light-tx dark:text-dark-tx">
      <ChartColumn class="w-6 h-6" />
      <h1 class="text-2xl font-semibold">Anzahl Prompts</h1>
    </div>
    {#if data}
      <span class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        {formatWeek(data.week_start, data.week_end)}
      </span>
    {/if}
  </div>

  {#if error}
    <div class="flex items-center gap-3 p-4 rounded border
                bg-light-re-2 dark:bg-dark-re-2
                border-light-re dark:border-dark-re
                text-dark-tx dark:text-light-tx">
      <CircleX class="w-5 h-5 shrink-0" />
      <span class="text-sm">{error}</span>
    </div>
  {:else if loading}
    <div class="flex items-center gap-3 p-4 rounded border
                bg-light-bg dark:bg-dark-bg
                border-light-tx-2 dark:border-dark-tx-2
                text-light-tx-2 dark:text-dark-tx-2">
      <LoaderCircle class="w-5 h-5 animate-spin shrink-0" />
      <span>Lädt…</span>
    </div>
  {:else if data}
    <div class="overflow-x-auto rounded border border-light-tx-2 dark:border-dark-tx-2">
      <table class="border-collapse text-xs">
        <thead>
          <tr class="bg-light-ui-3 dark:bg-dark-ui-3">
            <th class="sticky left-0 z-10 bg-light-ui-3 dark:bg-dark-ui-3
                       px-3 py-2 text-left text-light-tx-2 dark:text-dark-tx-2
                       border-b border-r border-light-tx-2 dark:border-dark-tx-2
                       min-w-[5rem]">
              Tag / h
            </th>
            {#each {length: 24} as _, h}
              <th class="px-1 py-2 text-center font-normal
                         text-light-tx-2 dark:text-dark-tx-2
                         border-b border-r border-light-tx-2 dark:border-dark-tx-2
                         min-w-[2.5rem]">
                {h}
              </th>
            {/each}
          </tr>
        </thead>
        <tbody>
          {#each DAY_NAMES as dayName, dow}
            <tr class="border-b border-light-tx-2 dark:border-dark-tx-2">
              <td class="sticky left-0 z-10 bg-light-bg dark:bg-dark-bg
                         px-3 py-1 font-medium text-light-tx dark:text-dark-tx
                         border-r border-light-tx-2 dark:border-dark-tx-2">
                {dayName}
              </td>
              {#each {length: 24} as _, hour}
                {@const cell = data.cells.find(c => c.dow === dow && c.hour === hour)}
                {@const count = cell?.count ?? 0}
                {@const maxCount = Math.max(...data.cells.map(c => c.count), 1)}
                {@const opacity = count === 0 ? 0 : Math.max(0.15, count / maxCount)}
                <td
                  title="{count} Nachricht{count !== 1 ? 'en' : ''}"
                  class="border-r border-light-tx-2 dark:border-dark-tx-2 h-8 w-10
                         {count === 0
                           ? 'bg-light-ui-3 dark:bg-dark-ui-3'
                           : 'bg-light-gr-2 dark:bg-dark-gr-2'}"
                  style={count > 0 ? `opacity: ${opacity.toFixed(2)}` : ''}
                >
                </td>
              {/each}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

    <div class="mt-2 flex items-center gap-4 text-xs text-light-tx-2 dark:text-dark-tx-2">
      <span class="flex items-center gap-1">
        <span class="inline-block w-4 h-4 rounded bg-light-gr-2 dark:bg-dark-gr-2"
              style="opacity: 0.2"></span>
        wenige Nachrichten
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block w-4 h-4 rounded bg-light-gr-2 dark:bg-dark-gr-2"
              style="opacity: 1.0"></span>
        viele Nachrichten
      </span>
    </div>
  {/if}

</div>
