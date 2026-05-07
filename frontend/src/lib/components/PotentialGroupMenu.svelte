<script>
  import { MoreHorizontal, Check, X } from 'lucide-svelte'
  import { createTeachingGroup, addExclusion } from '$lib/api.js'

  let { classGroupId, subjectId, className, onrefresh } = $props()
  let open = $state(false)
  let loading = $state(false)

  async function handleConfirm() {
    loading = true
    await createTeachingGroup(classGroupId, subjectId)
    if (onrefresh) onrefresh()
    loading = false
    open = false
  }

  async function handleExclude() {
    loading = true
    await addExclusion(classGroupId, subjectId)
    if (onrefresh) onrefresh()
    loading = false
    open = false
  }

  function toggle(e) {
    e.stopPropagation()
    open = !open
  }
</script>

<div class="relative" onclick={(e) => e.stopPropagation()}>
  <button
    onclick={toggle}
    disabled={loading}
    class="p-1 rounded-full hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
           text-light-tx-2 dark:text-dark-tx-2 disabled:opacity-50 transition-colors"
    aria-label="Potenzielle Gruppenmenü"
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
        onclick={(e) => { e.stopPropagation(); handleConfirm() }}
        disabled={loading}
        class="w-full text-left px-4 py-2 text-sm text-light-tx dark:text-dark-tx
               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-50
               transition-colors flex items-center gap-2"
      >
        <Check size={14} />
        {loading ? 'Bestätigen...' : `Ich unterrichte das in ${className}`}
      </button>
      <button
        onclick={(e) => { e.stopPropagation(); handleExclude() }}
        disabled={loading}
        class="w-full text-left px-4 py-2 text-sm text-light-tx dark:text-dark-tx
               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 disabled:opacity-50
               transition-colors flex items-center gap-2"
      >
        <X size={14} />
        {loading ? 'Ablehnen...' : 'Ich unterrichte das nicht'}
      </button>
    </div>
  {/if}
</div>
