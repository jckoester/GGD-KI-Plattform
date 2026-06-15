<script>
  import { ueColor, UE_PALETTE } from '$lib/planner.js'

  const {
    units = [],
    balance = null,
    onCreateUnit,
    onEditUnit = null,
  } = $props()

  function balanceForUnit(unitId) {
    return balance?.items.find(b => b.ue_node_id === unitId) ?? null
  }

  function progressWidth(item) {
    if (!item || !item.soll_std || item.soll_std <= 0) return 0
    return Math.min(100, Math.round((item.zugewiesen / item.soll_std) * 100))
  }

  function progressColor(item) {
    if (!item) return 'bg-light-ui-3 dark:bg-dark-ui-3'
    if (!item.soll_std) return 'bg-light-ui-3 dark:bg-dark-ui-3'
    const ratio = item.zugewiesen / item.soll_std
    if (ratio > 1.05) return 'bg-orange-400'
    if (ratio >= 0.9) return 'bg-green-400'
    return 'bg-light-bl dark:bg-dark-bl'
  }
</script>

<div class="border-b border-light-ui-3 dark:border-dark-ui-3 bg-light-bg dark:bg-dark-bg px-4 py-3">
  <div class="flex items-center justify-between mb-2">
    <h3 class="text-xs font-semibold uppercase tracking-wide text-light-tx-2 dark:text-dark-tx-2">
      Unterrichtseinheiten
    </h3>
    <div class="flex items-center gap-4 text-xs text-light-tx-2 dark:text-dark-tx-2">
      {#if balance}
        <span>
          <span class="font-medium text-light-tx dark:text-dark-tx">{balance.total_slots}</span> Slots gesamt
        </span>
        {#if balance.unzugewiesen > 0}
          <span class="text-orange-600 dark:text-orange-400">
            <span class="font-medium">{balance.unzugewiesen}</span> nicht zugewiesen
          </span>
        {/if}
      {/if}
      <button
        onclick={onCreateUnit}
        class="px-2.5 py-1 rounded-md text-xs font-medium
               bg-primary dark:bg-primary-dark text-white hover:opacity-90 transition-opacity"
      >
        + UE
      </button>
    </div>
  </div>

  {#if !units.length}
    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 italic">
      Noch keine Unterrichtseinheiten. Mit "+ UE" anlegen.
    </p>
  {:else}
    <div class="flex flex-wrap gap-3">
      {#each units as unit (unit.id)}
        {@const bal = balanceForUnit(unit.id)}
        <div class="flex items-center gap-2 min-w-0 group/ue">
          <div
            class="w-3 h-3 rounded-full flex-shrink-0"
            style="background-color: {ueColor(unit)}"
          ></div>
          <div class="min-w-0">
            <button
              type="button"
              onclick={() => onEditUnit?.(unit)}
              disabled={!onEditUnit}
              title={onEditUnit ? `„${unit.title}" bearbeiten` : unit.title}
              class="flex items-center gap-1 text-xs font-medium text-light-tx dark:text-dark-tx
                     max-w-[180px] text-left
                     {onEditUnit ? 'hover:text-light-bl dark:hover:text-dark-bl transition-colors cursor-pointer' : 'cursor-default'}"
            >
              <span class="truncate">{unit.title}</span>
              {#if onEditUnit}
                <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
                     class="flex-shrink-0 opacity-0 group-hover/ue:opacity-60" aria-hidden="true">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              {/if}
            </button>
            {#if bal}
              <div class="flex items-center gap-1.5 mt-0.5">
                <div class="w-20 h-1.5 bg-light-ui-3 dark:bg-dark-ui-3 rounded-full overflow-hidden">
                  <div
                    class="h-full rounded-full transition-all {progressColor(bal)}"
                    style="width: {progressWidth(bal)}%"
                  ></div>
                </div>
                <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                  {bal.zugewiesen}{bal.soll_std ? `/${bal.soll_std}` : ''} Std
                  {#if bal.puffer > 0}
                    <span class="text-orange-500">(+{bal.puffer})</span>
                  {/if}
                </span>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>
