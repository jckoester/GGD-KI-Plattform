<script>
  import { slide } from 'svelte/transition'
  import { ChevronDown, ChevronRight } from 'lucide-svelte'
  import SubjectIcon from './SubjectIcon.svelte'

  let { section } = $props()

  let expanded = $state(true)

  function toggle() { expanded = !expanded }

  function formatCount(n) {
    if (n === 0) return '–'
    return String(n)
  }
</script>

{#if section.type === 'student'}
  <!-- Schüler-Zeile: Fachname, Anzahl, Link -->
  <a
    href={section.slug ? `/subjects/${section.slug}` : '/history'}
    class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm
           text-light-tx dark:text-dark-tx
           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
  >
    <SubjectIcon name={section.icon} size={15} color={section.color} />
    <span class="flex-1 truncate">
      {section.name}{section.qualifier ? ` · ${section.qualifier}` : ''}
    </span>
    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0">
      {formatCount(section.count)}
    </span>
  </a>

{:else if section.type === 'teacher'}
  <!-- Lehrkraft-Kopfzeile: aufklappbar -->
  <button
    onclick={toggle}
    class="flex items-center gap-2 w-full px-3 py-1.5 rounded-md text-sm
           text-light-tx dark:text-dark-tx font-medium
           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
  >
    <SubjectIcon name={section.icon} size={15} color={section.color} />
    <span class="flex-1 text-left truncate">{section.name}</span>
    {#if expanded}
      <ChevronDown size={14} class="shrink-0 text-light-tx-2 dark:text-dark-tx-2" />
    {:else}
      <ChevronRight size={14} class="shrink-0 text-light-tx-2 dark:text-dark-tx-2" />
    {/if}
  </button>

  {#if expanded}
    <div transition:slide={{ duration: 150 }}>
      {#each section.groups as group (group.groupId)}
        <a
          href={`/subjects/${section.slug}/groups/${group.groupId}`}
          class="flex items-center gap-2 pl-7 pr-3 py-1.5 rounded-md text-sm
                 text-light-tx-2 dark:text-dark-tx-2
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
        >
          <span class="flex-1 truncate">{group.name}</span>
          <span class="text-xs shrink-0">{formatCount(group.count)}</span>
        </a>
      {/each}
    </div>
  {/if}
{/if}
