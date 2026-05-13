<script>
  import { goto } from '$app/navigation'
  import { Bot } from 'lucide-svelte'
  import SubjectIcon from './SubjectIcon.svelte'

  let { assistant, subject = null, groups = [] } = $props()

  function startChat() {
    goto(`/chat?assistant_id=${assistant.id}`)
  }

  function scopeLabel() {
    if (assistant.scope === 'teaching_group' && assistant.scope_group_id) {
      const g = groups.find(g => g.id === assistant.scope_group_id)
      return g?.name ?? 'Klasse'
    }
    if (assistant.scope === 'grade' && assistant.min_grade != null) {
      return assistant.min_grade === assistant.max_grade
        ? `Jahrgang ${assistant.min_grade}`
        : `Jahrgang ${assistant.min_grade}–${assistant.max_grade}`
    }
    return 'alle'
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
    {#if subject}
      <SubjectIcon name={subject.icon} size={14} color={subject.color} />
    {:else}
      <Bot size={14} class="text-light-tx-2 dark:text-dark-tx-2 shrink-0" />
    {/if}
    <span class="font-medium text-sm text-light-tx dark:text-dark-tx truncate flex-1">
      {assistant.name}
    </span>
    <span class="text-xs px-1.5 py-0.5 rounded bg-light-ui-2 dark:bg-dark-ui-2
                 text-light-tx-2 dark:text-dark-tx-2 shrink-0">
      {scopeLabel()}
    </span>
  </div>
  {#if assistant.description}
    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 line-clamp-2 leading-relaxed">
      {assistant.description}
    </p>
  {/if}
</button>
