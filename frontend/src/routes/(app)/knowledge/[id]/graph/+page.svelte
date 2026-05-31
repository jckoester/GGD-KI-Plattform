<script>
  import { page } from '$app/stores'
  import GraphExplorer from '$lib/components/GraphExplorer.svelte'
</script>

<div class="h-full flex flex-col">
  <div class="px-6 py-3 border-b border-light-ui-2 dark:border-dark-ui-2 flex-shrink-0">
    <a
      href="/knowledge/{$page.params.id}"
      class="text-sm text-light-tx-2 dark:text-dark-tx-2
             hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
      ← Zurück zum Knoten
    </a>
  </div>
  <div class="flex-1 min-h-0">
    <GraphExplorer nodeId={$page.params.id} />
  </div>
</div>
