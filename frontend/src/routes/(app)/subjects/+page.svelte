<script>
    import { visibleSidebarSubjectSections } from "$lib/stores/sidebarSections.js";
    import { conversationCountsBySubject } from "$lib/stores/conversationCounts.js";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import { LayoutGrid, List } from "lucide-svelte";

    // Ansicht: 'grid' | 'list', aus localStorage (Default: 'grid')
    let viewMode = $state(localStorage.getItem("subjects_view_mode") ?? "grid");

    function setViewMode(mode) {
        viewMode = mode;
        localStorage.setItem("subjects_view_mode", mode);
    }

    // Nutzerrelevante Fächer, dedupliziert nach subjectId (Schüler können mehrere
    // Gruppen im gleichen Fach haben — auf der Übersicht zählt das Fach einmal)
    const sorted = $derived.by(() => {
        const seen = new Set()
        return $visibleSidebarSubjectSections.filter(s => {
            if (seen.has(s.subjectId)) return false
            seen.add(s.subjectId)
            return true
        })
    });

    function chatCount(section) {
        return $conversationCountsBySubject[String(section.subjectId)] ?? 0;
    }

    function chatLabel(n) {
        return n === 1 ? "1 Chat" : `${n} Chats`;
    }
</script>

<div class="h-full overflow-y-auto p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
        <h1 class="text-xl font-semibold text-light-tx dark:text-dark-tx">
            Meine Fächer
        </h1>
        <div class="flex items-center gap-1">
            <button
                onclick={() => setViewMode("grid")}
                class="p-1.5 rounded-md transition-colors
                       {viewMode === 'grid'
                    ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
                    : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                aria-label="Kachelansicht"
            >
                <LayoutGrid size={16} />
            </button>
            <button
                onclick={() => setViewMode("list")}
                class="p-1.5 rounded-md transition-colors
                       {viewMode === 'list'
                    ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx'
                    : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                aria-label="Listenansicht"
            >
                <List size={16} />
            </button>
        </div>
    </div>

    <!-- Leerer Zustand -->
    {#if sorted.length === 0}
        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
            Dir sind noch keine Fächer zugeordnet.
        </p>

        <!-- Kachelansicht -->
    {:else if viewMode === "grid"}
        <div class="grid grid-cols-2 gap-3">
            {#each sorted as section (section.subjectId)}
                <div class="flex flex-col gap-2 p-4 rounded-xl border border-light-ui-3 dark:border-dark-ui-3
                           bg-light-bg dark:bg-dark-bg-2 transition-colors
                           hover:border-primary dark:hover:border-primary-dark">
                    <a href="/subjects/{section.slug}" class="flex items-center gap-2 min-w-0">
                        <SubjectIcon
                            name={section.icon}
                            size={20}
                            color={section.color}
                        />
                        <span
                            class="font-medium text-sm text-light-tx dark:text-dark-tx truncate"
                        >
                            {section.name}
                        </span>
                    </a>
                    {#if section.groups?.length > 0}
                        <div class="flex flex-wrap gap-x-2 gap-y-1">
                            {#each section.groups as group (group.groupId)}
                                <a
                                    href="/subjects/{section.slug}/groups/{group.groupId}"
                                    class="text-xs text-light-tx-2 dark:text-dark-tx-2
                                           hover:text-primary dark:hover:text-primary-dark transition-colors"
                                >
                                    {group.name}
                                </a>
                            {/each}
                        </div>
                    {/if}
                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                        {chatLabel(chatCount(section))}
                    </span>
                </div>
            {/each}
        </div>

        <!-- Listenansicht -->
    {:else}
        <div
            class="flex flex-col divide-y divide-light-ui-2 dark:divide-dark-ui-2
                    border border-light-ui-3 dark:border-dark-ui-3 rounded-xl overflow-hidden"
        >
            {#each sorted as section (section.subjectId)}
                <div class="flex items-center gap-3 px-4 py-3
                           bg-light-bg dark:bg-dark-bg-2
                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2
                           transition-colors">
                    <SubjectIcon
                        name={section.icon}
                        size={18}
                        color={section.color}
                    />
                    <div class="flex-1 min-w-0">
                        <a
                            href="/subjects/{section.slug}"
                            class="block text-sm font-medium text-light-tx dark:text-dark-tx truncate
                                   hover:text-primary dark:hover:text-primary-dark transition-colors"
                        >
                            {section.name}
                        </a>
                        {#if section.groups?.length > 0}
                            <div class="flex flex-wrap gap-x-2">
                                {#each section.groups as group (group.groupId)}
                                    <a
                                        href="/subjects/{section.slug}/groups/{group.groupId}"
                                        class="text-xs text-light-tx-2 dark:text-dark-tx-2
                                               hover:text-primary dark:hover:text-primary-dark transition-colors"
                                    >
                                        {group.name}
                                    </a>
                                {/each}
                            </div>
                        {/if}
                    </div>
                    <span
                        class="text-xs text-light-tx-2 dark:text-dark-tx-2 shrink-0"
                    >
                        {chatLabel(chatCount(section))}
                    </span>
                </div>
            {/each}
        </div>
    {/if}
</div>
