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

  // ── Fach aus Store ────────────────────────────────────────────────────────
  const subject = $derived(
    $subjects.find(s => s.slug === $page.params.slug) ?? null
  )

  // ── Rolle ─────────────────────────────────────────────────────────────────
  const isTeacher = $derived($user?.roles?.includes('teacher') ?? false)

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
      const opts = { limit: LIMIT, offset: append ? conversations.length : 0, subjectId: subject.id }
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
  <!-- Linke Gruppe-Navigationsleiste (nur Lehrkraft) -->
  {#if isTeacher && myGroupsForSubject.length > 0}
    <nav class="w-48 shrink-0 border-r border-light-ui-2 dark:border-dark-ui-2
                flex flex-col gap-1 p-3 overflow-y-auto">
      <p class="text-xs font-semibold uppercase tracking-wide
                text-light-tx-2 dark:text-dark-tx-2 px-2 mb-1">
        Unterrichtsgruppen
      </p>
      {#each myGroupsForSubject as group (group.id)}
        <a
          href={`/subjects/${subject.slug}/groups/${group.id}`}
          class="px-2 py-1.5 rounded-md text-sm text-light-tx dark:text-dark-tx
                 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors truncate"
        >
          {group.name}
        </a>
      {/each}
    </nav>
  {/if}

  <!-- Hauptinhalt -->
  <main class="flex-1 overflow-y-auto p-6 max-w-3xl">
    <!-- Kopfzeile -->
    {#if subject}
      <div class="flex items-center gap-3 mb-6">
        <SubjectIcon name={subject.icon} size={28} color={subject.color} />
        <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">{subject.name}</h1>
      </div>
    {/if}

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
      <h2 class="text-xs font-semibold uppercase tracking-wide
                 text-light-tx-2 dark:text-dark-tx-2 mb-3">
        Meine Chats
      </h2>

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
  </main>
</div>
