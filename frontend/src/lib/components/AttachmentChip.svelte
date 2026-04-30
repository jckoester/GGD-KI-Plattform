<script>
  import { Loader2, Paperclip, X, AlertCircle } from 'lucide-svelte'

  let { filename, status, error = null, onremove } = $props()
</script>

<div
  class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs border
         {status === 'error'
           ? 'border-light-re dark:border-dark-re text-light-re dark:text-dark-re bg-red-50 dark:bg-red-950'
           : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2 bg-light-bg-2 dark:bg-dark-bg-2'}"
  title={error ?? filename}
>
  {#if status === 'uploading'}
    <Loader2 class="w-3 h-3 animate-spin shrink-0" />
  {:else if status === 'error'}
    <AlertCircle class="w-3 h-3 shrink-0" />
  {:else}
    <Paperclip class="w-3 h-3 shrink-0" />
  {/if}

  <span class="max-w-[120px] truncate">{filename}</span>

  <button
    type="button"
    onclick={onremove}
    class="ml-0.5 rounded-full hover:bg-light-ui dark:hover:bg-dark-ui p-0.5 shrink-0"
    aria-label="Anhang entfernen"
  >
    <X class="w-3 h-3" />
  </button>
</div>
