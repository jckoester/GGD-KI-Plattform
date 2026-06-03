<script>
  import { page } from '$app/stores'
  import { goto } from '$app/navigation'
  import { subjects, subjectMap } from '$lib/stores/subjects.js'
  import { assistants } from '$lib/stores/assistants.js'
  import { myTeachingGroups } from '$lib/stores/myGroups.js'
  import { user } from '$lib/stores/user.js'
  import { refreshConversationCounts } from '$lib/stores/conversationCounts.js'
  import { getConversations } from '$lib/api.js'
  import AssistantCard from '$lib/components/AssistantCard.svelte'
  import SubjectIcon from '$lib/components/SubjectIcon.svelte'
  import ConversationMenu from '$lib/components/ConversationMenu.svelte'
  import KnowledgeNodeList from '$lib/components/KnowledgeNodeList.svelte'

  // ── Fach aus Store ────────────────────────────────────────────────────────
  const subject = $derived(
    $subjects.find(s => s.slug === $page.params.slug) ?? null
  )

  // ── Rolle ─────────────────────────────────────────────────────────────────
  const isTeacher = $derived($user?.roles?.includes('teacher') ?? false)

  // ── Tab-Zustand (URL-basiert, damit Zurück-Navigation den Tab erhält) ──────
  const activeTab = $derived($page.url.searchParams.get('tab') ?? 'uebersicht')

  // Import für Curriculum-Tab
  import CurriculumList from '$lib/components/CurriculumList.svelte'

  // ── Eigene Unterrichtsgruppen dieses Fachs (Lehrkraft) ────────────────────
  const myGroupsForSubject = $derived(
    isTeacher && subject
      ? $myTeachingGroups.filter(g => g.subject_id === subject.id)
      : []
  )

  // ── Assistenten dieses Fachs ───────────────────────────────────────────────
  const subjectAssistants = $derived(
    subject
      ? $assistants.filter(a => a.subject_id === subject.id)
      : []
  )

  // ── Konversationen (paginiert) ─────────────────────────────────────────────
  let conversations = $state([])
  let total = $state(0)
  let loading = $state(true)
  let loadingMore = $state(false)
  const LIMIT = 25

  async function loadConversations(append = false) {
    if (!subject) return
    if (append) loadingMore = true
    else loading = true
    try {
      const opts = { limit: LIMIT, offset: append ? conversations.length : 0, subjectId: subject.id, excludeGroups: true }
      const data = await getConversations(opts)
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
    // Läuft bei Mount und bei Fach-Wechsel (Navigation zwischen Fächern)
    if (subject) loadConversations()
  })
</script>

<div class="flex min-h-0 flex-1">
  <main class="flex-1 overflow-y-auto p-6 max-w-3xl">
    <!-- Kopfzeile -->
    {#if subject}
      <div class="flex items-center gap-3 mb-6">
        <SubjectIcon name={subject.icon} size={28} color={subject.color} />
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">{subject.name}</h1>
      </div>
    {/if}

    <!-- Unterrichtsgruppen-Chips (nur Lehrkraft) -->
    {#if isTeacher && myGroupsForSubject.length > 0}
      <div class="flex flex-wrap gap-2 mb-4">
        {#each myGroupsForSubject as group (group.id)}
          {@const isActive = $page.url.pathname === `/subjects/${subject.slug}/groups/${group.id}`}
          <a
            href={`/subjects/${subject.slug}/groups/${group.id}`}
            class="inline-flex items-center px-3 py-1.5 rounded-full text-sm border transition-colors
                   {isActive
                     ? 'border-primary dark:border-primary-dark bg-primary/10 dark:bg-primary-dark/10 text-primary dark:text-primary-dark font-medium'
                     : 'border-light-ui-3 dark:border-dark-ui-3 text-light-tx dark:text-dark-tx hover:border-primary dark:hover:border-primary-dark'}"
          >
            {group.name}
          </a>
        {/each}
      </div>
    {/if}

    <!-- Tab-Leiste (nur Lehrkraft) -->
    {#if isTeacher}
      <nav class="flex gap-1 border-b border-light-ui-2 dark:border-dark-ui-2 mb-6 -mx-6 px-6">
        {#each [
          { id: 'uebersicht', label: 'Übersicht' },
          { id: 'curriculum', label: 'Curriculum' },
          { id: 'kontext',    label: 'Kontext'   },
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
    {/if}

    <!-- Tab-Inhalte -->
    {#if activeTab === 'uebersicht' || !isTeacher}
      <!-- Assistenten -->
      {#if subjectAssistants.length > 0}
        <section class="mb-8">
          <h2 class="text-xs font-semibold uppercase tracking-wide
                     text-light-tx-2 dark:text-dark-tx-2 mb-3">
            Assistenten
          </h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {#each subjectAssistants as assistant (assistant.id)}
              <AssistantCard {assistant} {subject} groups={myGroupsForSubject} />
            {/each}
          </div>
        </section>
      {/if}

      <!-- Meine Chats -->
      <section class="mb-8">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wide
                     text-light-tx-2 dark:text-dark-tx-2">
            Meine Chats
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
            Noch keine Chats in diesem Fach.
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
      </section>

      <!-- Artefakte & Informationen (Phase 5) -->
      <section>
        <h2 class="text-xs font-semibold uppercase tracking-wide
                   text-light-tx-2 dark:text-dark-tx-2 mb-3">
          Artefakte & Informationen
        </h2>
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
          Dieser Bereich wird in Phase 5 mit verknüpften Dokumenten und Vektoren befüllt.
        </p>
      </section>
    {:else if activeTab === 'curriculum' && isTeacher}
      <CurriculumList subjectId={subject?.id} subjectSlug={subject?.slug} showNewButton={true} />
    {:else if activeTab === 'kontext' && isTeacher}
      <KnowledgeNodeList
        fixedSubjectSlug={subject?.slug}
        showSubjectFilter={false}
        showNewButton={true}
      />
    {/if}
  </main>
</div>
