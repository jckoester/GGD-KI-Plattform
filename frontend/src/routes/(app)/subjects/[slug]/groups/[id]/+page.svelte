<script>
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'
  import { subjectMap } from '$lib/stores/subjects.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { refreshConversationCounts } from '$lib/stores/conversationCounts.js'
  import { getConversations } from '$lib/api.js'
  import ConversationMenu from '$lib/components/ConversationMenu.svelte'
  import SubjectIcon from '$lib/components/SubjectIcon.svelte'

  // ── Gruppe + Fach aus Stores ──────────────────────────────────────────────
  const group = $derived(
    $myTeachingGroups.find(g => g.id === Number($page.params.id)) ?? null
  )
  const subject = $derived(
    group ? ($subjectMap[group.subject_id] ?? null) : null
  )

  // ── Tab-Zustand ────────────────────────────────────────────────────────────
  let activeTab = $state('vorbereitung')

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
        onclick={() => { activeTab = tab.id }}
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
      <div class="divide-y divide-light-ui-2 dark:divide-dark-ui-2">
        {#each conversations as conv (conv.id)}
          <div class="flex items-center gap-2 py-2.5 group">
            <a
              href={`/chat?id=${conv.id}`}
              class="flex-1 min-w-0 flex items-center gap-3
                     hover:text-primary dark:hover:text-primary-dark transition-colors"
            >
              <span class="text-sm text-light-tx dark:text-dark-tx truncate flex-1">
                {conv.title ?? 'Unbenannter Chat'}
              </span>
              <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0">
                {conv.last_message_at
                  ? new Date(conv.last_message_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
                  : ''}
              </span>
            </a>
            <div class="opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              <ConversationMenu
                conversationId={conv.id}
                title={conv.title}
                subject_id={conv.subject_id}
                group_id={conv.group_id}
                onDeleted={() => handleConversationDeleted(conv.id)}
                iconSize={14}
              />
            </div>
          </div>
        {/each}
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

  <!-- Tab: Kontext (Platzhalter) -->
  {:else if activeTab === 'kontext'}
    <div class="py-8 text-center text-light-tx-2 dark:text-dark-tx-2">
      <p class="font-medium mb-2 text-light-tx dark:text-dark-tx">Kontext</p>
      <p class="text-sm max-w-sm mx-auto">
        Hier werden in Phase 5 verknüpfte Dokumente und Vektoren dieser Unterrichtsgruppe
        einsehbar und bearbeitbar sein.
      </p>
    </div>
  {/if}

</div>
