<script>
    import PageBody from '$lib/components/PageBody.svelte'
    import StufenHinweis from '$lib/components/StufenHinweis.svelte'
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { getRecentConversations, getVorschauChats } from "$lib/api.js";
    import { kannVorschauBetreten } from "$lib/vorschau.js";
    import { Loader2, Bot } from "lucide-svelte";
    import ConversationMenu from "$lib/components/ConversationMenu.svelte";
    import { refreshConversations } from "$lib/stores/conversations.js";
    import { History, ArrowLeft } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";
    import SubjectIcon from "$lib/components/SubjectIcon.svelte";
    import { subjectMap } from "$lib/stores/subjects.js";
    import { myGroups } from "$lib/stores/myGroups.js";
    import { user } from "$lib/stores/user.js";
    import { gruppenMarke, chatTooltip } from "$lib/gruppenmarke.js";

    let conversations = $state([]);
    // Die Unterrichtsgruppe steht nur für Lehrkräfte in der Zeile — siehe
    // `gruppenMarke`: Aus Schülersicht ist die Gruppe das Fach, und das zeigt
    // bereits das farbige Symbol.
    const istLehrkraft = $derived(
        $user?.roles.includes('teacher') || $user?.roles.includes('admin'),
    );
    let loading = $state(true);
    let error = $state(null);
    let offset = $state(0);
    let total = $state(0);
    let hasMore = $state(false);
    // Chats aus der Vorschau stehen in einer eigenen Liste (0.29). Nur außerhalb der
    // Vorschau — in ihr gibt es ohnehin nur diese.
    let liste = $state("eigene");
    const vorschauListeAnbieten = $derived(kannVorschauBetreten($user));

    const limit = 25;

    async function loadConversations() {
        loading = true;
        error = null;
        try {
            const data = liste === "vorschau"
                ? await getVorschauChats(limit, offset)
                : await getRecentConversations(limit, offset);
            conversations = [...conversations, ...data.items];
            total = data.total;
            hasMore = offset + data.items.length < data.total;
        } catch (err) {
            error = err.message ?? "Fehler beim Laden der Chats";
        } finally {
            loading = false;
        }
    }

    function loadMore() {
        offset += limit;
        loadConversations();
    }

    function resetAndLoad() {
        offset = 0;
        conversations = [];
        loadConversations();
    }

    onMount(resetAndLoad);

    function formatDateTime(dateString) {
        if (!dateString) return "";
        const date = new Date(dateString);
        return date.toLocaleString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function navigateToChat(id) {
        goto(`/chat?id=${id}`);
    }

    function handleDeleted(deletedId) {
        conversations = conversations.filter((c) => c.id !== deletedId);
        total -= 1;
        hasMore = offset + conversations.length < total;
        refreshConversations();
    }
</script>

<PageBody breit>
  <StufenHinweis eintrag="history" />
    <button
        onclick={() => history.back()}
        class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
    >
        <ArrowLeft class="w-4 h-4" /> Zurück
    </button>

    <div class="max-w-4xl mx-auto">
        <div
            class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx"
        >
            <History class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Meine Chats</h1>
        </div>

        {#if vorschauListeAnbieten}
            <div class="flex gap-2 mb-4 text-sm" role="group" aria-label="Welche Chats">
                {#each [["eigene", "Meine Chats"], ["vorschau", "Aus der Vorschau"]] as [wert, label] (wert)}
                    <button
                        onclick={() => { liste = wert; resetAndLoad(); }}
                        aria-pressed={liste === wert}
                        class="px-3 py-1 rounded-lg border border-light-ui-3 dark:border-dark-ui-3
                               {liste === wert
                                   ? 'bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx font-medium'
                                   : 'text-light-tx-2 dark:text-dark-tx-2 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2'}"
                    >{label}</button>
                {/each}
            </div>
            {#if liste === "vorschau"}
                <p class="mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2">
                    Chats, die du in der Vorschau als Schüler:in geführt hast. Fortsetzen lassen
                    sie sich nur in der Vorschau; nach 30 Tagen werden sie gelöscht.
                </p>
            {/if}
        {/if}

        {#if loading && conversations.length === 0}
            <div class="flex items-center justify-center py-12">
                <div class="flex flex-col items-center gap-2 text-gray-500">
                    <Loader2 class="w-6 h-6 animate-spin" />
                    <p>Chats werden geladen...</p>
                </div>
            </div>
        {:else if error}
            <ErrorBanner message={error} />
        {:else if conversations.length === 0}
            <div class="text-center py-12 text-light-tx-3 dark:text-dark-tx-3">
                <p class="text-lg">
                    {liste === "vorschau" ? "Noch keine Chats aus der Vorschau." : "Noch keine Chats gespeichert."}
                </p>
            </div>
        {:else}
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr
                            class="border-b border-light-ui-3 dark:border-dark-ui-3"
                        >
                            <th
                                class="px-4 py-3 text-sm font-medium text-light-tx-2 dark:text-dark-tx-2"
                            >
                                Titel
                            </th>
                            <th
                                class="px-4 py-3 text-sm font-medium text-light-tx-2 dark:text-dark-tx-2"
                            >
                                Letzte Aktivität
                            </th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {#each conversations as conv}
                            <tr
                                class=" border-b border-light-ui-3 dark:border-dark-ui-3 hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors cursor-pointer"
                                onclick={() => navigateToChat(conv.id)}
                            >
                                <td
                                    class="px-4 py-3 text-light-tx dark:text-dark-tx"
                                >
                                    <div class="flex items-center gap-2">
                                        {#if conv.subject_id}
                                            <SubjectIcon
                                                name={$subjectMap[
                                                    conv.subject_id
                                                ]?.icon ?? null}
                                                color={$subjectMap[
                                                    conv.subject_id
                                                ]?.color ?? null}
                                                size={16}
                                                class="shrink-0"
                                            />
                                        {/if}
                                        {#if conv.vorschau}
                                            <span
                                                class="shrink-0 px-1.5 py-0.5 rounded text-xs
                                                       bg-light-ye-bg dark:bg-dark-ye-bg text-light-tx dark:text-dark-tx"
                                                title="Aus der Vorschau"
                                            >Klasse {conv.vorschau.jahrgang}</span>
                                        {/if}
                                        {#if conv.assistant_name}
                                            <Bot
                                                class="w-4 h-4 shrink-0 text-light-bl dark:text-dark-bl"
                                                title={conv.assistant_name}
                                            />
                                        {/if}
                                        <!-- Die Unterrichtsgruppe, sofern der Chat einer
                                             zugeordnet ist. Hier ist Platz für den Namen;
                                             in der Sidebar steht er nur im Tooltip. -->
                                        {#if gruppenMarke(conv.group_id, $myGroups, { istLehrkraft })}
                                            <span
                                                class="shrink-0 max-w-[12rem] truncate px-1.5 py-0.5 rounded
                                                       bg-light-ui-2 dark:bg-dark-ui-2
                                                       text-xs text-light-tx-2 dark:text-dark-tx-2"
                                                title={gruppenMarke(conv.group_id, $myGroups, { istLehrkraft })}
                                            >
                                                {gruppenMarke(conv.group_id, $myGroups, { istLehrkraft })}
                                            </span>
                                        {/if}
                                        <span
                                            title={chatTooltip(
                                                conv.title,
                                                gruppenMarke(conv.group_id, $myGroups, { istLehrkraft }),
                                            )}
                                            >{conv.title ??
                                                "Unbenannter Chat"}</span
                                        >
                                    </div>
                                </td>
                                <td
                                    class="px-4 py-3 text-sm text-light-tx-3 dark:text-dark-tx-3"
                                >
                                    {formatDateTime(conv.last_message_at)}
                                </td>
                                <td>
                                    <ConversationMenu
                                        conversationId={conv.id}
                                        title={conv.title}
                                        subject_id={conv.subject_id ?? null}
                                        group_id={conv.group_id ?? null}
                                        onDeleted={handleDeleted}
                                    />
                                </td>
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>

            {#if hasMore && !loading}
                <div class="mt-6 text-center">
                    <button
                        onclick={loadMore}
                        class="px-4 py-2 bg-light-ui-2 dark:bg-dark-ui-2 text-light-tx dark:text-dark-tx
                   rounded-lg hover:bg-light-ui-3 dark:hover:bg-dark-ui-3 transition-colors"
                    >
                        Weitere laden
                    </button>
                </div>
            {/if}

            {#if loading && conversations.length > 0}
                <div class="mt-4 flex justify-center">
                    <Loader2 class="w-5 h-5 animate-spin" />
                </div>
            {/if}
        {/if}
    </div>
</PageBody>
