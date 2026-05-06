<script>
  import { page } from '$app/stores'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'

  const group = $derived(
    $myTeachingGroups.find(g => g.id === Number($page.params.id)) ?? null
  )
</script>

<div class="flex flex-col items-center justify-center h-64 gap-3
            text-light-tx-2 dark:text-dark-tx-2">
  {#if group}
    <p class="text-lg font-semibold text-light-tx dark:text-dark-tx">{group.name}</p>
  {/if}
  <p class="text-sm">Diese Ansicht wird in Kürze verfügbar sein.</p>
</div>
