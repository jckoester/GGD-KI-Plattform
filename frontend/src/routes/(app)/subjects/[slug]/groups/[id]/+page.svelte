<script>
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'
  import { subjectMap } from '$lib/stores/subjects.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { assistants } from '$lib/stores/assistants.js'
  import { refreshConversationCounts } from '$lib/stores/conversationCounts.js'
  import { getConversations } from '$lib/api.js'
  import ConversationMenu from '$lib/components/ConversationMenu.svelte'
  import SubjectIcon from '$lib/components/SubjectIcon.svelte'
  import AssistantCard from '$lib/components/AssistantCard.svelte'
  import KnowledgeNodeList from '$lib/components/KnowledgeNodeList.svelte'

  // ── Gruppe + Fach aus Stores ──────────────────────────────────────────────
  const group = $derived(
    $myTeachingGroups.find(g => g.id === Number($page.params.id)) ?? null
  )
  const subject = $derived(
    group ? ($subjectMap[group.subject_id] ?? null) : null
  )
  // Voreingestellte Jahrgangsstufe aus dem Fach ableiten
  const defaultGrade = $derived(subject?.min_grade ?? null)

  // ── Assistenten für diese Gruppe ──────────────────────────────────────────
  const groupAssistants = $derived(
    subject
      ? $assistants.filter(a =>
          a.subject_id === subject.id &&
          (a.scope === 'all' ||
           a.scope === 'subject_department' ||
           a.scope_group_id === group?.id)
        )
      : []
  )

  // ── Tab-Zustand (URL-basiert, damit Zurück-Navigation den Tab erhält) ──────
  const activeTab = $derived($page.url.searchParams.get('tab') ?? 'vorbereitung')

  // ── Konversationen (Tab "Vorbereitung") ───────────────────────────────────
  let conversations = $state([])
  let total = $state(0)
  let loading = $state(true)
  let loadingMore = $state(false)
  const LIMIT = 25

  async function loadConversations(append = false) {
    if (!group) return
    if (append) loadingMore = true
    else loading = true
    try {
      const data = await getConversations({
        limit: LIMIT,
        offset: append ? conversations.length : 0,
        groupId: group.id,
      })
      if (append) {
        conversations = [...conversations, ...data.items]
      } else {
        conversations = data.items
      }
      total = data.total
    } finally {
      loading = false
      loadingMore = false
    }
  }

  function handleConversationDeleted(id) {
    conversations = conversations.filter(c => c.id !== id)
    total = Math.max(0, total - 1)
    refreshConversationCounts()
  }

  $effect(() => {
    // Läuft bei Mount und bei Gruppen-Wechsel
    if (group) loadConversations()
  })
</script>

<!-- Seitenkopf mit Breadcrumb -->
<div class="border-b border-light-ui-2 dark:border-dark-ui-2 px-6 py-4">
  <div class="flex items-center gap-2 text-sm text-light-tx-2 dark:text-dark-tx-2 mb-1">
    {#if subject}
      <a href={`/subjects/${subject.slug}`}
         class="hover:text-light-tx dark:hover:text-dark-tx transition-colors flex items-center gap-1.5">
        <SubjectIcon name={subject.icon} size={14} color={subject.color} />
        {subject.name}
      </a>
      <span>/</span>
    {/if}
    <span class="text-light-tx dark:text-dark-tx font-medium">{group?.name ?? '…'}</span>
  </div>

  <!-- Tab-Leiste -->
  <nav class="flex gap-1 -mb-px mt-3">
    {#each [
      { id: 'vorbereitung', label: 'Vorbereitung' },
      { id: 'klasse',       label: 'Klasse'       },
      { id: 'archiv',       label: 'Archiv'        },
      { id: 'kontext',      label: 'Kontext'       },
    ] as tab (tab.id)}
      <button
        onclick={() => goto(`?tab=${tab.id}`, { replaceState: true, keepFocus: true })}
        class="px-4 py-2 text-sm font-medium border-b-2 transition-colors
               {activeTab === tab.id
                 ? 'border-primary text-light-bl dark:text-dark-bl dark:border-primary-dark'
                 : 'border-transparent text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx'}"
      >
        {tab.label}
      </button>
    {/each}
  </nav>
</div>

<!-- Tab-Inhalt -->
<div class="flex-1 overflow-y-auto p-6 max-w-3xl">

  <!-- Tab: Vorbereitung -->
  {#if activeTab === 'vorbereitung'}
    {#if groupAssistants.length > 0}
      <section class="mb-6">
        <h2 class="text-xs font-semibold uppercase tracking-wide
                   text-light-tx-2 dark:text-dark-tx-2 mb-3">
          Assistenten
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {#each groupAssistants as assistant (assistant.id)}
            <AssistantCard {assistant} {subject} groups={$myTeachingGroups} />
          {/each}
        </div>
      </section>
    {/if}
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xs font-semibold uppercase tracking-wide
                 text-light-tx-2 dark:text-dark-tx-2">
        Meine Chats in dieser Gruppe
      </h2>
      <button
        onclick={() => goto('/chat')}
        class="text-sm px-3 py-1.5 rounded-md bg-primary dark:bg-primary-dark
               text-white font-medium hover:opacity-90 transition-opacity"
      >
        + Neuer Chat
      </button>
    </div>

    {#if loading}
      <div class="flex justify-center py-8">
        <span class="text-light-tx-2 dark:text-dark-tx-2 text-sm">Wird geladen…</span>
      </div>
    {:else if conversations.length === 0}
      <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
        Noch keine Chats in dieser Unterrichtsgruppe.
      </p>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-light-ui-3 dark:border-dark-ui-3">
              <th class="px-4 py-3 text-sm font-medium text-light-tx-2 dark:text-dark-tx-2">Titel</th>
              <th class="px-4 py-3 text-sm font-medium text-light-tx-2 dark:text-dark-tx-2">letzte Aktivität</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each conversations as conv (conv.id)}
              <tr
                class="border-b border-light-ui-3 dark:border-dark-ui-3
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors cursor-pointer"
                onclick={() => goto(`/chat?id=${conv.id}`)}
              >
                <td class="px-4 py-3 text-light-tx dark:text-dark-tx">
                  {conv.title ?? 'Unbenannter Chat'}
                </td>
                <td class="px-4 py-3 text-sm text-light-tx-3 dark:text-dark-tx-3 whitespace-nowrap">
                  {conv.last_message_at
                    ? new Date(conv.last_message_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })
                    : ''}
                </td>
                <td>
                  <ConversationMenu
                    conversationId={conv.id}
                    title={conv.title}
                    subject_id={conv.subject_id}
                    group_id={conv.group_id}
                    onDeleted={() => handleConversationDeleted(conv.id)}
                    iconSize={14}
                  />
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      {#if conversations.length < total}
        <button
          onclick={() => loadConversations(true)}
          disabled={loadingMore}
          class="mt-4 text-sm text-light-tx-2 dark:text-dark-tx-2
                 hover:text-light-tx dark:hover:text-dark-tx transition-colors
                 disabled:opacity-50"
        >
          {loadingMore ? 'Wird geladen…' : `Weitere laden (${total - conversations.length})`}
        </button>
      {/if}
    {/if}

  <!-- Tab: Klasse (Platzhalter) -->
  {:else if activeTab === 'klasse'}
    <div class="py-8 text-center text-light-tx-2 dark:text-dark-tx-2">
      <p class="font-medium mb-2 text-light-tx dark:text-dark-tx">Klassen-Ansicht</p>
      <p class="text-sm max-w-sm mx-auto">
        Hier werden in Phase 7 die freigegebenen Assistenten für diese Unterrichtsgruppe
        sowie Steuerelemente zur Freigabe und zum Sichtbarkeitsfenster erscheinen.
      </p>
    </div>

  <!-- Tab: Archiv (Platzhalter) -->
  {:else if activeTab === 'archiv'}
    <div class="py-8 text-center text-light-tx-2 dark:text-dark-tx-2">
      <p class="font-medium mb-2 text-light-tx dark:text-dark-tx">Archiv</p>
      <p class="text-sm max-w-sm mx-auto">
        Hier werden in Phase 7 vergangene Schuljahre mit archivierten Chats, Materialien
        und Assistenten dieser Unterrichtsgruppe zugänglich sein.
      </p>
    </div>

  <!-- Tab: Kontext -->
  {:else if activeTab === 'kontext'}
    <KnowledgeNodeList
      fixedGroupId={group?.id}
      showSubjectFilter={false}
      showNewButton={true}
      initialGrade={defaultGrade}
    />
  {/if}

</div>
