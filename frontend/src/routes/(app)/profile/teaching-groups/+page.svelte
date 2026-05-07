<script>
  import { onMount } from 'svelte'
  import { Check, Trash2, X } from 'lucide-svelte'
  import { myTeachingGroups, refreshMyGroups } from '$lib/stores/myGroups.js'
  import { potentialTeachingGroups, refreshPotentialTeachingGroups } from '$lib/stores/potentialTeachingGroups.js'
  import { getExclusions, removeExclusion, createTeachingGroup, deleteTeachingGroup, addExclusion } from '$lib/api.js'
  import { subjectMap } from '$lib/stores/subjects.js'
  import SubjectIcon from '$lib/components/SubjectIcon.svelte'

  let exclusions = $state([])
  let loading = $state(true)
  let error = $state(null)

  async function loadData() {
    loading = true
    error = null
    try {
      const exclData = await getExclusions()
      exclusions = exclData
    } catch (err) {
      error = err.message || 'Fehler beim Laden der Daten'
    } finally {
      loading = false
    }
  }

  async function handleConfirm(classGroupId, subjectId) {
    try {
      await createTeachingGroup(classGroupId, subjectId)
      await refreshMyGroups()
      await refreshPotentialTeachingGroups()
    } catch (err) {
      error = err.message || 'Fehler beim Bestätigen'
    }
  }

  async function handleExclude(classGroupId, subjectId) {
    try {
      await addExclusion(classGroupId, subjectId)
      await refreshPotentialTeachingGroups()
      await loadData()
    } catch (err) {
      error = err.message || 'Fehler beim Ablehnen'
    }
  }

  async function handleRemoveExclusion(classGroupId, subjectId) {
    try {
      await removeExclusion(classGroupId, subjectId)
      await createTeachingGroup(classGroupId, subjectId)
      await refreshMyGroups()
      await refreshPotentialTeachingGroups()
      await loadData()
    } catch (err) {
      error = err.message || 'Fehler beim Reaktivieren'
    }
  }

  async function handleDeleteGroup(groupId) {
    try {
      await deleteTeachingGroup(groupId)
      await refreshMyGroups()
      await refreshPotentialTeachingGroups()
    } catch (err) {
      error = err.message || 'Fehler beim Löschen'
    }
  }

  onMount(() => {
    loadData()
    refreshPotentialTeachingGroups()
  })
</script>

<div class="p-6 max-w-2xl">
  <div class="mb-6">
    <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">Unterrichtsgruppen verwalten</h1>
    <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mt-1">
      Hier kannst du deine Unterrichtsgruppen verwalten und abgelehnte Kombinationen wiederherstellen.
    </p>
  </div>

  {#if error}
    <div class="mb-4 p-3 bg-red-100 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-lg">
      <p class="text-sm text-red-700 dark:text-red-300">{error}</p>
    </div>
  {/if}

  <!-- Sektion 1: Eigene Unterrichtsgruppen -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-4">
      Meine Unterrichtsgruppen
    </h2>

    {#if loading}
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen...</p>
    {:else if $myTeachingGroups.length === 0}
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Du hast noch keine Unterrichtsgruppen.
      </p>
    {:else}
      <div class="space-y-3">
        {#each $myTeachingGroups as group (group.id)}
          {@const subj = group.subject_id ? $subjectMap[group.subject_id] : null}
          {@const href = subj ? `/subjects/${subj.slug}/groups/${group.id}` : null}
          <div class="flex items-center justify-between p-3 rounded-lg
                      bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-2 dark:border-dark-ui-2">
            <div class="flex items-center gap-3 min-w-0">
              {#if subj}
                <SubjectIcon name={subj.icon} size={20} color={subj.color} />
              {/if}
              <div class="min-w-0">
                {#if href}
                  <a {href}
                     class="font-medium text-light-tx dark:text-dark-tx hover:text-light-bl dark:hover:text-dark-bl transition-colors truncate block">
                    {group.name}
                  </a>
                {:else}
                  <p class="font-medium text-light-tx dark:text-dark-tx truncate">{group.name}</p>
                {/if}
                {#if subj}
                  <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">{subj.name}</p>
                {/if}
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span class="text-xs px-2 py-0.5 rounded-full
                          {group.sso_group_id
                            ? 'bg-light-ui-3 dark:bg-dark-ui-3 text-light-tx-2 dark:text-dark-tx-2'
                            : 'bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark'}">
                {group.sso_group_id ? 'SSO' : 'Manuell'}
              </span>
              {#if !group.sso_group_id}
                <button
                  onclick={() => handleDeleteGroup(group.id)}
                  class="p-1.5 rounded-lg text-light-re dark:text-dark-re
                         hover:bg-red-100 dark:hover:bg-red-900/20 transition-colors"
                  title="Löschen"
                >
                  <Trash2 size={16} />
                </button>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Sektion 2: Vorgeschlagene Unterrichtsgruppen -->
  {#if $potentialTeachingGroups.length > 0}
    <section class="mb-8">
      <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-1">
        Vorgeschlagene Unterrichtsgruppen
      </h2>
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
        Basierend auf deinen Klassen- und Fachschaft-Mitgliedschaften. Bestätige oder lehne ab.
      </p>
      <div class="space-y-3">
        {#each $potentialTeachingGroups as pot (pot.class_group_id + '-' + pot.subject_id)}
          <div class="flex items-center justify-between p-3 rounded-lg
                      bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-2 dark:border-dark-ui-2">
            <div class="flex items-center gap-3 min-w-0">
              {#if pot.subject_icon || pot.subject_color}
                <SubjectIcon name={pot.subject_icon} size={20} color={pot.subject_color} />
              {/if}
              <div class="min-w-0">
                <p class="font-medium text-light-tx dark:text-dark-tx truncate">{pot.class_name}</p>
                <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">{pot.subject_name}</p>
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button
                onclick={() => handleConfirm(pot.class_group_id, pot.subject_id)}
                class="px-3 py-1.5 rounded-lg bg-primary dark:bg-primary-dark
                       text-white text-sm font-medium hover:opacity-90 transition-opacity
                       flex items-center gap-1.5"
                title="Ich unterrichte dieses Fach in dieser Klasse"
              >
                <Check size={14} />
                Bestätigen
              </button>
              <button
                onclick={() => handleExclude(pot.class_group_id, pot.subject_id)}
                class="p-1.5 rounded-lg text-light-tx-2 dark:text-dark-tx-2
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                title="Ich unterrichte dieses Fach nicht in dieser Klasse"
              >
                <X size={16} />
              </button>
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Sektion 3: Abgelehnte Kombinationen -->
  <section class="mb-8">
    <h2 class="text-lg font-semibold text-light-tx dark:text-dark-tx mb-4">
      Abgelehnte Kombinationen
    </h2>

    {#if loading}
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen...</p>
    {:else if exclusions.length === 0}
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Keine abgelehnten Kombinationen.
      </p>
    {:else}
      <div class="space-y-3">
        {#each exclusions as excl (excl.class_group_id + '-' + excl.subject_id)}
          <div class="flex items-center justify-between p-3 rounded-lg
                      bg-light-bg-2 dark:bg-dark-bg-2 border border-light-ui-2 dark:border-dark-ui-2">
            <div class="flex items-center gap-3 min-w-0">
              {#if $subjectMap[excl.subject_id]}
                <SubjectIcon name={$subjectMap[excl.subject_id]?.icon} size={20} color={$subjectMap[excl.subject_id]?.color} />
              {/if}
              <div class="min-w-0">
                <p class="font-medium text-light-tx dark:text-dark-tx truncate">{excl.class_name}</p>
                {#if $subjectMap[excl.subject_id]}
                  <p class="text-xs text-light-tx-2 dark:text-dark-tx-2">{$subjectMap[excl.subject_id].name}</p>
                {/if}
              </div>
            </div>
            <button
              onclick={() => handleRemoveExclusion(excl.class_group_id, excl.subject_id)}
              class="px-3 py-1.5 rounded-lg bg-primary dark:bg-primary-dark
                     text-white text-sm font-medium hover:opacity-90 disabled:opacity-50
                     transition-opacity flex items-center gap-1.5"
            >
              <Check size={14} />
              Reaktivieren
            </button>
          </div>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Hinweis -->
  <section class="text-sm text-light-tx-2 dark:text-dark-tx-2">
    <p>
      <strong>Hinweis:</strong> Unterrichtsgruppen aus dem SSO-System werden automatisch verwaltet
      und können hier nicht gelöscht werden. Manuell angelegte Gruppen (ohne SSO-Verknüpfung) können gelöscht werden.
    </p>
  </section>
</div>
