<script>
  import { Loader2, Paperclip, X, AlertCircle } from 'lucide-svelte'
  import { CHIP_AKZENT, CHIP_FORM, CHIP_ICON } from '$lib/chip_form.js'

  let { filename, status, error = null, onremove } = $props()
</script>

<div
  class="{CHIP_FORM} {status === 'error' ? CHIP_AKZENT.re : CHIP_AKZENT.neutral}"
  title={error ?? filename}
>
  {#if status === 'uploading'}
    <Loader2 size={CHIP_ICON} class="animate-spin shrink-0" />
  {:else if status === 'error'}
    <AlertCircle size={CHIP_ICON} class="shrink-0 text-light-re dark:text-dark-re" />
  {:else}
    <Paperclip size={CHIP_ICON} class="shrink-0" />
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
