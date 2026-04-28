<script>
    import { onMount } from "svelte";
    import { goto } from "$app/navigation";
    import { getRecentConversations } from "$lib/api.js";
    import { user } from "$lib/stores/user.js";
    import { Loader2 } from "lucide-svelte";
    import ConversationMenu from "$lib/components/ConversationMenu.svelte";
    import { refreshConversations } from "$lib/stores/conversations.js";
    import { History, ArrowLeft } from "lucide-svelte";
    import ErrorBanner from "$lib/components/ErrorBanner.svelte";

    let conversations = $state([]);
    let loading = $state(true);
    let error = $state(null);
    let offset = $state(0);
    let total = $state(0);
    let hasMore = $state(false);

    const limit = 25;

    async function loadConversations() {
        loading = true;
        error = null;
        try {
            const data = await getRecentConversations(limit, offset);
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

<button
    onclick={() => history.back()}
    class="flex items-center gap-1 mb-4 text-sm text-light-tx-2 dark:text-dark-tx-2 hover:text-light-tx dark:hover:text-dark-tx transition-colors"
>
    <ArrowLeft class="w-4 h-4" /> Zurück
</button>

<div class="h-full overflow-y-auto p-6">
    <div class="max-w-4xl mx-auto">
        <div
            class="flex items-center gap-2 mb-6 text-light-tx dark:text-dark-tx"
        >
            <History class="w-6 h-6" />
            <h1 class="text-2xl font-semibold">Meine Chats</h1>
        </div>

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
                <p class="text-lg">Noch keine Chats gespeichert.</p>
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
                                    {conv.title ?? "Unbenannter Chat"}
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
</div>
