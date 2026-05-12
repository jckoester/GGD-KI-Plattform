<script>
    import { goto } from '$app/navigation'
    import { MessageSquare, ChevronRight } from 'lucide-svelte'
    import { user } from '$lib/stores/user.js'
    import { potentialTeachingGroups } from '$lib/stores/potentialTeachingGroups.js'
    import { groupsConfig } from '$lib/stores/groupsConfig.js'

    const displayName = sessionStorage.getItem('display_name') ?? ''

    function greeting() {
        const h = new Date().getHours()
        if (h < 11) return 'Guten Morgen'
        if (h < 17) return 'Guten Tag'
        return 'Guten Abend'
    }

    const isTeacher = $derived($user?.roles?.includes('teacher') ?? false)

    const showGroupsHint = $derived(
        isTeacher &&
        $groupsConfig.allow_manual_teaching_groups &&
        $potentialTeachingGroups.length > 0
    )

    let inputText = $state('')

    function startChat() {
        const q = inputText.trim()
        if (!q) {
            goto('/chat')
            return
        }
        goto(`/chat?q=${encodeURIComponent(q)}`)
    }

    function handleKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            startChat()
        }
    }
</script>

<div class="h-full overflow-y-auto flex flex-col items-center justify-center px-4 py-12">
    <div class="w-full max-w-xl flex flex-col gap-8">

        <!-- Begrüßung -->
        <div class="text-center">
            <h1 class="text-3xl font-bold text-light-tx dark:text-dark-tx">
                {greeting()}{displayName ? `, ${displayName}` : ''}
            </h1>
            <p class="mt-2 text-light-tx-2 dark:text-dark-tx-2">
                Womit kann ich dir heute helfen?
            </p>
        </div>

        <!-- Chat-Eingabe -->
        <div class="relative">
            <textarea
                bind:value={inputText}
                onkeydown={handleKeydown}
                placeholder="Stell eine Frage oder gib ein Thema ein …"
                rows="3"
                class="w-full resize-none rounded-xl border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg dark:bg-dark-bg-2
                       text-light-tx dark:text-dark-tx
                       placeholder:text-light-tx-3 dark:placeholder:text-dark-tx-3
                       px-4 py-3 pr-14 text-sm leading-relaxed
                       focus:outline-none focus:border-primary dark:focus:border-primary-dark
                       transition-colors"
            ></textarea>
            <button
                onclick={startChat}
                class="absolute bottom-3 right-3 p-2 rounded-lg
                       bg-primary dark:bg-primary-dark text-white
                       hover:opacity-90 transition-opacity disabled:opacity-40"
                disabled={!inputText.trim()}
                aria-label="Chat starten"
            >
                <MessageSquare size={16} />
            </button>
        </div>

        <!-- Hinweis auf offene Unterrichtsgruppen (nur Lehrkräfte) -->
        {#if showGroupsHint}
            <a
                href="/profile/teaching-groups"
                class="flex items-center justify-between gap-3 px-4 py-3 rounded-xl
                       border border-light-ui-3 dark:border-dark-ui-3
                       bg-light-bg-2 dark:bg-dark-bg-2
                       hover:border-primary dark:hover:border-primary-dark
                       transition-colors group"
            >
                <div class="min-w-0">
                    <p class="text-sm font-medium text-light-tx dark:text-dark-tx">
                        {$potentialTeachingGroups.length}
                        {$potentialTeachingGroups.length === 1
                            ? 'vorgeschlagene Unterrichtsgruppe'
                            : 'vorgeschlagene Unterrichtsgruppen'}
                    </p>
                    <p class="text-xs text-light-tx-2 dark:text-dark-tx-2 mt-0.5">
                        Bestätigen oder ablehnen unter Profil → Unterrichtsgruppen
                    </p>
                </div>
                <ChevronRight
                    size={16}
                    class="text-light-tx-2 dark:text-dark-tx-2 shrink-0
                           group-hover:text-primary dark:group-hover:text-primary-dark
                           transition-colors"
                />
            </a>
        {/if}

    </div>
</div>
