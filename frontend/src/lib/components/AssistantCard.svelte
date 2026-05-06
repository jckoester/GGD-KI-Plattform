<script>
  import { goto } from '$app/navigation'
  import { Bot } from 'lucide-svelte'

  let { assistant } = $props()

  function startChat() {
    goto(`/chat?assistant_id=${assistant.id}`)
  }
</script>

<button
  onclick={startChat}
  class="flex flex-col gap-1.5 p-3 rounded-lg border border-light-ui-2 dark:border-dark-ui-2
         bg-light-bg-2 dark:bg-dark-bg-2
         hover:border-light-ui-3 dark:hover:border-dark-ui-3
         hover:bg-light-ui dark:hover:bg-dark-ui
         transition-colors text-left w-full"
>
  <div class="flex items-center gap-2">
    <Bot size={16} class="text-light-tx-2 dark:text-dark-tx-2 shrink-0" />
    <span class="font-medium text-sm text-light-tx dark:text-dark-tx truncate">
      {assistant.name}
    </span>
  </div>
  {#if assistant.description}
    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 line-clamp-2 leading-relaxed">
      {assistant.description}
    </p>
  {/if}
</button>
