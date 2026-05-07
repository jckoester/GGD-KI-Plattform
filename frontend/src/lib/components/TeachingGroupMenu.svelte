<script>
  import { MoreHorizontal } from 'lucide-svelte'
  import { deleteTeachingGroup } from '$lib/api.js'

  let { groupId, className, onrefresh } = $props()
  let open = $state(false)
  let loading = $state(false)

  async function handleDelete() {
    loading = true
    await deleteTeachingGroup(groupId)
    if (onrefresh) onrefresh()
    loading = false
    open = false
  }

  function toggle(e) {
    e.stopPropagation()
    open = !open
  }

  function close() {
    open = false
  }
</script>

<div class="relative" onclick={(e) => e.stopPropagation()}>
  <button
    onclick={toggle}
    disabled={loading}
    class="p-1 rounded-full hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
           text-light-tx-2 dark:text-dark-tx-2 disabled:opacity-50 transition-colors"
    aria-label="Gruppenmenü"
  >
    <MoreHorizontal size={14} />
  </button>

  {#if open}
    <div
      class="absolute right-0 top-full mt-1 z-50 w-48 bg-light-bg dark:bg-dark-bg rounded-lg shadow-lg
                  border border-light-ui-2 dark:border-dark-ui-2"
      onclick={(e) => e.stopPropagation()}
    >
      <button
        onclick={(e) => { e.stopPropagation(); handleDelete() }}
        disabled={loading}
        class="w-full text-left px-4 py-2 text-sm text-light-re dark:text-dark-re
               hover:bg-red-100 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
      >
        {loading ? 'Löschen...' : 'Ich unterrichte das nicht mehr'}
      </button>
    </div>
  {/if}
</div>
