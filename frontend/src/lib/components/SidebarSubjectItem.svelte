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
  <!-- Lehrkraft-Kopfzeile: Link zum Fach + optionaler Chevron-Toggle -->
  <div class="flex items-center gap-0 rounded-md
              hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors">
    <a
      href={`/subjects/${section.slug}`}
      class="flex items-center gap-2 flex-1 min-w-0 px-3 py-1.5 text-sm
             text-light-tx dark:text-dark-tx font-medium"
    >
      <SubjectIcon name={section.icon} size={15} color={section.color} />
      <span class="flex-1 truncate">{section.name}</span>
    </a>
    {#if section.groups.length > 0}
      <button
        onclick={toggle}
        class="px-2 py-1.5 text-light-tx-2 dark:text-dark-tx-2 shrink-0"
        aria-label={expanded ? 'Zuklappen' : 'Aufklappen'}
      >
        {#if expanded}
          <ChevronDown size={14} />
        {:else}
          <ChevronRight size={14} />
        {/if}
      </button>
    {/if}
  </div>

  {#if expanded && section.groups.length > 0}
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
