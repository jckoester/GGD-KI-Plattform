<script>
  import { goto } from '$app/navigation'
  import { Bot } from 'lucide-svelte'
  import SubjectIcon from './SubjectIcon.svelte'
  import { neuerChatPfad } from '$lib/chatziel.js'
  import { stufenText } from '$lib/assistentenliste.js'
  import { BADGE } from '$lib/badges.js'
  import { assistentKosten } from '$lib/modellangaben.js'
  import { budget } from '$lib/stores/budget.js'

  // `groupId`: Auf der Gruppenseite gehört der Chat zu dieser Gruppe — wie bei „+ Neuer Chat".
  // Ohne sie leitete der Server die Gruppe nur aus dem Fach des Assistenten ab; ein
  // allgemeiner Assistent hat keins, und der Chat kannte den Unterricht der Gruppe nicht.
  let { assistant, subject = null, groups = [], groupId = null } = $props()

  function startChat() {
    goto(neuerChatPfad({ assistantId: assistant.id, groupId }))
  }

  // Klassenstufen gehen vor (0.27): „Kl. 8–13“ sagt mehr als „alle“.
  function scopeLabel() {
    if (stufenText(assistant)) return stufenText(assistant)
    if (assistant.scope === 'teaching_group' && assistant.scope_group_id) {
      const g = groups.find(g => g.id === assistant.scope_group_id)
      return g?.name ?? 'Klasse'
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
    {#if assistentKosten(assistant, $budget?.eur_usd_rate, $budget?.einheiten_je_euro).marke}
      <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0"
            title="Geschätzte Kosten je Nachricht, samt Prompt und Dokumenten">{assistentKosten(assistant, $budget?.eur_usd_rate, $budget?.einheiten_je_euro).marke}</span>
    {/if}
    <span class="{BADGE} shrink-0">
      {scopeLabel()}
    </span>
  </div>
  {#if assistant.description}
    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 line-clamp-2 leading-relaxed">
      {assistant.description}
    </p>
  {/if}
</button>
