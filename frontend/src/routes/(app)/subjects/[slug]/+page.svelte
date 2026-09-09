<script>
    /**
     * Die Fachseite — zwei grundverschiedene Aufgaben, je nach Rolle.
     *
     * **Für Schüler:innen ist sie eine Weiche.** Es gibt für sie keine Fach-Ebene:
     * Jeder ihrer Chats hängt an einer Unterrichtsgruppe (der Fach-Wähler bietet
     * nichts anderes an). Eine Seite „Mathematik" mit eigenem Inhalt wäre eine
     * Seite ohne Inhalt — bis 09/2026 war sie das auch, nur unbemerkt: Sie fragte
     * ihre Chats mit `exclude_groups` ab, also nach `group_id IS NULL`, und das
     * trifft auf keinen einzigen Schülerchat zu.
     *
     * **Für Lehrkräfte bündelt sie.** Sie führt die Unterrichtsgruppen zusammen und
     * trägt, was Fachbezug *ohne* Gruppenbezug hat: persönliche Fach-Chats,
     * Curriculum, Bildungsplan, die Bestände der Fachschaft.
     */
    import PageBody from '$lib/components/PageBody.svelte'
    import { fachSammlungen } from "$lib/collections.js";
    import NodeTypeIcon from "$lib/components/NodeTypeIcon.svelte";
    import { page } from "$app/stores";
    import { goto } from "$app/navigation";
    import { subjects } from "$lib/stores/subjects.js";
    import { BP_CURRICULUM_CONTENT_TYPES } from "$lib/taxonomy.js";
    import { assistants } from "$lib/stores/assistants.js";
    import { myTeachingGroups, myGroupsGeladen } from "$lib/stores/myGroups.js";
    import { conversationCountsByGroup, refreshConversationCounts } from "$lib/stores/conversationCounts.js";
    import { user } from "$lib/stores/user.js";
    import { getConversations, getFormerGroups } from "$lib/api.js";
    import { gruppenImFach, schuelerWeiche } from "$lib/gruppenseite.js";
    import AssistantCard from "$lib/components/AssistantCard.svelte";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import ConversationMenu from "$lib/components/ConversationMenu.svelte";
    import KnowledgeNodeList from "$lib/components/KnowledgeNodeList.svelte";
    import CurriculumList from "$lib/components/CurriculumList.svelte";
    import BildungsplanTree from "$lib/components/BildungsplanTree.svelte";
    import { Search } from "lucide-svelte";

    const subject = $derived(
        $subjects.find((s) => s.slug === $page.params.slug) ?? null,
    );

    // Admin ist eine Erweiterung der Lehrkraft-Rolle (CLAUDE.md, Rollenmodell)
    const isTeacher = $derived($user?.roles?.includes("teacher") ?? false);

    // ── Schüler-Weiche ────────────────────────────────────────────────────────
    const weiche = $derived(
        isTeacher ? null : schuelerWeiche($myTeachingGroups, subject?.id),
    );

    $effect(() => {
        // `replaceState`, damit „zurück" nicht in die Weiche zurückfällt und von
        // dort sofort wieder vorwärts leitet.
        if (weiche?.art === "weiterleiten") {
            goto(`/subjects/${$page.params.slug}/groups/${weiche.gruppe.id}`, {
                replaceState: true,
            });
        }
    });

    // ── Reiter (nur Lehrkraft) ────────────────────────────────────────────────
    const activeTab = $derived(
        $page.url.searchParams.get("tab") ?? "uebersicht",
    );

    const myGroupsForSubject = $derived(
        isTeacher ? gruppenImFach($myTeachingGroups, subject?.id) : [],
    );

    const subjectAssistants = $derived(
        subject ? $assistants.filter((a) => a.subject_id === subject.id) : [],
    );

    // ── Frühere Gruppen dieses Fachs (nur die Zahl, für den Hinweis) ──────────
    let fruehereGruppen = $state(0);

    $effect(() => {
        if (!subject || !isTeacher) return;
        const fach = subject.id;
        getFormerGroups(fach)
            .then((daten) => {
                if (subject?.id === fach) fruehereGruppen = daten.items?.length ?? 0;
            })
            // Das Archiv ist eine Zugabe; scheitert es, bleibt der Hinweis weg.
            .catch(() => {});
    });

    // ── Chats ohne Gruppenbezug ───────────────────────────────────────────────
    // `excludeGroups` ist **hier** richtig: Für Lehrkräfte gibt es persönliche
    // Fach-Chats ohne Gruppe. Auf der Gruppenseite wäre derselbe Parameter fatal.
    let conversations = $state([]);
    let total = $state(0);
    let loading = $state(true);
    let loadingMore = $state(false);
    const LIMIT = 25;

    async function loadConversations(append = false) {
        if (!subject || !isTeacher) return;
        if (append) loadingMore = true;
        else loading = true;
        try {
            const data = await getConversations({
                limit: LIMIT,
                offset: append ? conversations.length : 0,
                subjectId: subject.id,
                excludeGroups: true,
            });
            conversations = append ? [...conversations, ...data.items] : data.items;
            total = data.total;
        } finally {
            loading = false;
            loadingMore = false;
        }
    }

    function handleConversationDeleted(id) {
        conversations = conversations.filter((c) => c.id !== id);
        total = Math.max(0, total - 1);
        refreshConversationCounts();
    }

    $effect(() => {
        if (subject && isTeacher) loadConversations();
    });

    function chatZahl(groupId) {
        return parseInt($conversationCountsByGroup[String(groupId)] ?? 0);
    }

    function chatLabel(n) {
        return n === 1 ? "1 Chat" : `${n} Chats`;
    }

    function datum(wert) {
        if (!wert) return "";
        return new Date(wert).toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
    }
</script>

<PageBody>
    <!-- Kopfzeile -->
    {#if subject}
        <div class="flex items-center gap-3 mb-6">
            <SubjectIcon name={subject.icon} size={28} color={subject.color} />
            <h1 class="text-2xl font-bold text-light-tx dark:text-dark-tx">
                {subject.name}
            </h1>
        </div>
    {/if}

    {#if !isTeacher}
        <!-- ── Schüler:in: Weiche ──────────────────────────────────────────── -->
        {#if !$myGroupsGeladen || !subject || weiche?.art === "weiterleiten"}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">Wird geladen…</p>
        {:else if weiche?.art === "auswahl"}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 mb-4">
                Du hast in diesem Fach mehrere Gruppen. Welche meinst du?
            </p>
            <div class="flex flex-col gap-2">
                {#each weiche.gruppen as gruppe (gruppe.id)}
                    <a
                        href="/subjects/{subject.slug}/groups/{gruppe.id}"
                        class="flex items-center justify-between px-4 py-3 rounded-lg border
                               border-light-ui-3 dark:border-dark-ui-3
                               text-light-tx dark:text-dark-tx
                               hover:border-primary dark:hover:border-primary-dark transition-colors"
                    >
                        <span class="font-medium">{gruppe.name}</span>
                        <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                            {chatLabel(chatZahl(gruppe.id))}
                        </span>
                    </a>
                {/each}
            </div>
        {:else}
            <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                Dieses Fach ist dir zurzeit nicht zugeordnet. Wenn das nicht stimmt,
                melde dich bei deiner Lehrkraft — die Zuordnung kommt aus dem
                Schulkonto.
            </p>
        {/if}

    {:else}
        <!-- ── Lehrkraft: Bündler ──────────────────────────────────────────── -->
        <nav
            class="flex gap-1 border-b border-light-ui-2 dark:border-dark-ui-2 mb-6"
        >
            {#each [{ id: "uebersicht", label: "Übersicht" }, { id: "curriculum", label: "Curriculum" }, { id: "bildungsplan", label: "Bildungsplan" }, { id: "kontext", label: "weiterer Kontext" }] as tab (tab.id)}
                <button
                    onclick={() =>
                        goto(`?tab=${tab.id}`, {
                            replaceState: true,
                            keepFocus: true,
                        })}
                    class="px-4 py-2 text-sm font-medium border-b-2 transition-colors
                   {activeTab === tab.id
                        ? 'border-primary text-light-bl dark:text-dark-bl dark:border-primary-dark'
                        : 'border-transparent text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx'}"
                >
                    {tab.label}
                </button>
            {/each}
        </nav>

        {#if activeTab === "uebersicht"}
            <div class="divide-y divide-light-ui-2 dark:divide-dark-ui-2">
                <!-- Meine Gruppen: das eigentliche Ziel dieser Seite, deshalb
                     Karten statt Chips und an erster Stelle -->
                <section class="py-6 first:pt-0 last:pb-0">
                    <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-4">
                        Meine Gruppen
                    </h2>
                    {#if myGroupsForSubject.length === 0}
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                            In diesem Fach ist dir keine Unterrichtsgruppe zugeordnet.
                        </p>
                    {:else}
                        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                            {#each myGroupsForSubject as group (group.id)}
                                <a
                                    href="/subjects/{subject.slug}/groups/{group.id}"
                                    class="flex flex-col gap-1 p-4 rounded-xl border
                                           border-light-ui-3 dark:border-dark-ui-3
                                           bg-light-bg dark:bg-dark-bg-2 transition-colors
                                           hover:border-primary dark:hover:border-primary-dark"
                                >
                                    <span class="font-medium text-sm text-light-tx dark:text-dark-tx truncate">
                                        {group.name}
                                    </span>
                                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2">
                                        {chatLabel(chatZahl(group.id))}
                                    </span>
                                </a>
                            {/each}
                        </div>
                    {/if}

                    <!-- Ohne diesen Hinweis fände den Archiv-Reiter niemand: Er sitzt
                         auf der Gruppenseite, und wer dorthin will, hat die alte
                         Gruppe gerade nicht mehr in der Navigation. -->
                    {#if fruehereGruppen > 0 && myGroupsForSubject.length > 0}
                        <p class="mt-3 text-sm text-light-tx-2 dark:text-dark-tx-2">
                            Aus vergangenen Schuljahren
                            {fruehereGruppen === 1
                                ? "liegt eine Gruppe"
                                : `liegen ${fruehereGruppen} Gruppen`}
                            im
                            <a
                                href="/subjects/{subject.slug}/groups/{myGroupsForSubject[0].id}?tab=archiv"
                                class="text-light-bl dark:text-dark-bl hover:underline"
                            >
                                Archiv
                            </a>.
                        </p>
                    {/if}
                </section>

                <!-- Assistenten des Fachs -->
                {#if subjectAssistants.length > 0}
                    <section class="py-6 first:pt-0 last:pb-0">
                        <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-4">
                            Assistenten
                        </h2>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            {#each subjectAssistants as assistant (assistant.id)}
                                <AssistantCard
                                    {assistant}
                                    {subject}
                                    groups={myGroupsForSubject}
                                />
                            {/each}
                        </div>
                    </section>
                {/if}

                <!-- Ohne Gruppenbezug: persönliche Fach-Chats -->
                <section class="py-6 first:pt-0 last:pb-0">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2">
                            Ohne Gruppenbezug
                        </h2>
                        <button
                            onclick={() => goto("/chat")}
                            class="text-sm px-3 py-1.5 rounded-md bg-primary dark:bg-primary-dark
                                   text-white font-medium hover:opacity-90 transition-opacity"
                        >
                            + Neuer Chat
                        </button>
                    </div>

                    {#if loading}
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2 py-4">
                            Wird geladen…
                        </p>
                    {:else if conversations.length === 0}
                        <p class="text-sm text-light-tx-2 dark:text-dark-tx-2">
                            Keine Chats ohne Gruppenbezug. Was zu einer Gruppe gehört,
                            steht auf deren Seite.
                        </p>
                    {:else}
                        <div class="rounded-lg border border-light-ui-3 dark:border-dark-ui-3">
                            {#each conversations as conv (conv.id)}
                                <div
                                    class="flex items-center gap-2 px-4 py-2.5
                                           border-b last:border-b-0 border-light-ui-2 dark:border-dark-ui-2
                                           hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                                >
                                    <a
                                        href="/chat?id={conv.id}"
                                        class="flex-1 min-w-0 truncate text-sm text-light-tx dark:text-dark-tx"
                                    >
                                        {conv.title ?? "Unbenannter Chat"}
                                    </a>
                                    <span class="text-xs text-light-tx-2 dark:text-dark-tx-2 whitespace-nowrap">
                                        {datum(conv.last_message_at)}
                                    </span>
                                    <ConversationMenu
                                        conversationId={conv.id}
                                        title={conv.title}
                                        subject_id={conv.subject_id}
                                        group_id={conv.group_id}
                                        onDeleted={() => handleConversationDeleted(conv.id)}
                                        iconSize={14}
                                    />
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
                                {loadingMore
                                    ? "Wird geladen…"
                                    : `Weitere laden (${total - conversations.length})`}
                            </button>
                        {/if}
                    {/if}
                </section>

                <!-- Nachschlagen: die gepflegten Bestände der Fachschaft -->
                <section class="py-6 first:pt-0 last:pb-0">
                    <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2 mb-4">
                        Nachschlagen
                    </h2>
                    <div class="flex flex-wrap gap-2">
                        {#each fachSammlungen() as s (s.typ)}
                            <a
                                href="/knowledge/collections/{s.typ}?subject_id={subject?.id}"
                                title={s.beschreibung}
                                class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm
                                       rounded-md border border-light-ui-3 dark:border-dark-ui-3
                                       text-light-tx dark:text-dark-tx
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                            >
                                <NodeTypeIcon contentType={s.typ} size={16} />
                                {s.label}
                            </a>
                        {/each}
                        <a
                            href="/knowledge/search"
                            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm
                                   rounded-md border border-light-ui-3 dark:border-dark-ui-3
                                   text-light-tx dark:text-dark-tx
                                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
                        >
                            <Search size={16} />
                            Suche
                        </a>
                    </div>
                </section>
            </div>

        {:else if activeTab === "curriculum"}
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-base font-semibold text-light-tx-2 dark:text-dark-tx-2">
                    Curricula
                </h2>
                <!-- fach_code (Bildungsplan-Kürzel, z. B. 'M'), NICHT der Slug.
                     Fächer ohne fach_code → Link ohne Vorbelegung (frei wählbar). -->
                <a
                    href={subject?.fach_code
                        ? `/knowledge/curriculum/new?fach_code=${encodeURIComponent(subject.fach_code)}`
                        : "/knowledge/curriculum/new"}
                    class="text-sm px-3 py-1.5 rounded-md bg-primary dark:bg-primary-dark
                 text-white font-medium hover:opacity-90 transition-opacity"
                >
                    + Neues Curriculum
                </a>
            </div>
            <CurriculumList
                subjectId={subject?.id}
                subjectSlug={subject?.slug}
                showNewButton={false}
            />

        {:else if activeTab === "bildungsplan"}
            <BildungsplanTree
                subjectId={subject?.id}
                subjectSlug={subject?.slug}
            />

        {:else if activeTab === "kontext"}
            <KnowledgeNodeList
                fixedSubjectSlug={subject?.slug}
                showSubjectFilter={false}
                showNewButton={true}
                excludeContentTypes={BP_CURRICULUM_CONTENT_TYPES}
            />
        {/if}
    {/if}
</PageBody>
