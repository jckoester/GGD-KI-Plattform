<script>
  import { slide } from 'svelte/transition'
  import { ChevronDown, ChevronRight } from 'lucide-svelte'
  import SubjectIcon from './SubjectIcon.svelte'
  import TeachingGroupMenu from './TeachingGroupMenu.svelte'
  import PotentialGroupMenu from './PotentialGroupMenu.svelte'
  import { refreshMyGroups } from '$lib/stores/myGroups.js'
  import { refreshPotentialTeachingGroups } from '$lib/stores/potentialTeachingGroups.js'

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
    {#if section.groups.length > 0 || section.potentialGroups.length > 0}
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

  {#if expanded && (section.groups.length > 0 || section.potentialGroups.length > 0)}
    <div transition:slide={{ duration: 150 }}>
      <!-- Bestätigte Gruppen -->
      {#each section.groups as group (group.groupId)}
        <div class="flex items-center group/item pl-7 pr-1 rounded-md
                    hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors">
          <a href={`/subjects/${section.slug}/groups/${group.groupId}`}
             class="flex items-center gap-2 flex-1 py-1.5 text-sm
                    text-light-tx-2 dark:text-dark-tx-2 min-w-0">
            <span class="flex-1 truncate">{group.name}</span>
            <span class="text-xs shrink-0">{formatCount(group.count)}</span>
          </a>
          {#if group.isManual}
            <TeachingGroupMenu
              groupId={group.groupId}
              className={group.name}
              subjectId={section.subjectId}
              onrefresh={() => { refreshMyGroups(); refreshPotentialTeachingGroups() }}
            />
          {/if}
        </div>
      {/each}

      <!-- Trennlinie (nur wenn beide Listen nicht leer) -->
      {#if section.groups.length > 0 && section.potentialGroups.length > 0}
        <div class="mx-3 my-1 border-t border-light-ui-2 dark:border-dark-ui-2"></div>
      {/if}

      <!-- Potenzielle Gruppen -->
      {#each section.potentialGroups as pot (pot.classGroupId + '-' + pot.subjectId)}
        <div class="flex items-center pl-7 pr-1 rounded-md
                    hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors">
          <span class="flex-1 py-1.5 text-sm text-light-tx-3 dark:text-dark-tx-3 truncate">
            {pot.className}
          </span>
          <PotentialGroupMenu
            classGroupId={pot.classGroupId}
            subjectId={pot.subjectId}
            className={pot.className}
            onrefresh={() => { refreshMyGroups(); refreshPotentialTeachingGroups() }}
          />
        </div>
      {/each}
    </div>
  {/if}
{/if}
