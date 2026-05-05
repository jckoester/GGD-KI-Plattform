<script>
    import { branding } from "$lib/branding.js";
    import { slide } from "svelte/transition";
    import { goto } from "$app/navigation";
    import {
        Plus,
        ChevronDown,
        ChevronRight,
        History,
        ShieldCheck,
        BarChart2,
        PiggyBank,
        Bot,
        Settings,
    } from "lucide-svelte";
    import SidebarBottom from "./SidebarBottom.svelte";
    import {
        recentConversations,
        refreshConversations,
    } from "$lib/stores/conversations.js";
    import { user } from "$lib/stores/user.js";
    import { page } from "$app/stores";
    import { subjectMap } from "$lib/stores/subjects.js";
    import ConversationMenu from "$lib/components/ConversationMenu.svelte";

    const initials = (name) => name.slice(0, 2).toUpperCase();

    let {
        bgHeaderClass = "bg-light-bg dark:bg-dark-bg-2",
        textClass = "text-light-tx dark:text-dark-tx",
        borderClass = "border-light-ui-2 dark:border-dark-ui-2",
    } = $props();

    // Aufklappbarer Bereich für Letzte Chats
    let recentChatsOpen = $state(true);
    // Aufklappbarer Bereich für Assistenten
    let assistantsOpen = $state($page.url.pathname.startsWith('/assistants'));

    $effect(() => {
        if ($page.url.pathname.startsWith('/assistants')) assistantsOpen = true;
    });

    function toggleRecentChats() {
        recentChatsOpen = !recentChatsOpen;
    }

    function openRecentChats() {
        recentChatsOpen = true;
    }

    function toggleAssistants() {
        assistantsOpen = !assistantsOpen;
    }

    function formatDate(dateString) {
        if (!dateString) return "";
        const date = new Date(dateString);
        const now = new Date();

        // Prüfe ob heute
        const today = new Date(
            now.getFullYear(),
            now.getMonth(),
            now.getDate(),
        );
        const dateDate = new Date(
            date.getFullYear(),
            date.getMonth(),
            date.getDate(),
        );

        if (dateDate.getTime() === today.getTime()) {
            // Heute: nur Uhrzeit
            return date.toLocaleTimeString("de-DE", {
                hour: "2-digit",
                minute: "2-digit",
            });
        }

        // Prüfe ob gestern
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);
        if (dateDate.getTime() === yesterday.getTime()) {
            return "Gestern";
        }

        // Prüfe ob dieses Jahr
        if (date.getFullYear() === now.getFullYear()) {
            return date.toLocaleDateString("de-DE", {
                day: "2-digit",
                month: "2-digit",
            });
        }

        // Älter: voller Datum
        return date.toLocaleDateString("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        });
    }

    // Aktive Konversations-ID aus URL extrahieren
    const currentConversationId = $derived($page.url.searchParams.get("id"));

    // Limit aus User-Präferenzen
    const limit = $derived(
        $user?.preferences?.sidebar_recent_chats_limit ?? 10,
    );

    // Aktualisieren beim Ändern des Limits
    $effect(() => {
        refreshConversations(limit);
    });

    function handleDeleted(deletedId) {
        conversations = conversations.filter((c) => c.id !== deletedId);
        total -= 1;
        hasMore = offset + conversations.length < total;
        refreshConversations();
    }
</script>

<aside
    class="w-72 h-full bg-light-bg dark:bg-dark-bg-2 border-r border-light-ui-3 dark:border-dark-ui-3 flex flex-col"
    transition:slide={{ duration: 250, axis: "x" }}
>
    <!-- Sidebar-Header mit Branding -->
    <div
        class="h-14 border-b {bgHeaderClass} {borderClass} flex items-center px-4 flex-shrink-0"
    >
        {#if branding.logo_url_light || branding.logo_url_dark}
            {#if branding.logo_url_light}
                <img src={branding.logo_url_light} alt="Logo" class="h-8 w-auto dark:hidden" />
            {/if}
            {#if branding.logo_url_dark}
                <img src={branding.logo_url_dark} alt="Logo" class="h-8 w-auto hidden dark:block" />
            {/if}
        {:else}
            <div
                class="w-8 h-8 rounded-full bg-primary flex items-center justify-center
                       text-white text-xs font-bold select-none"
            >
                {initials(branding.name)}
            </div>
        {/if}
        <span class="ml-2 font-semibold {textClass}">{branding.name}</span>
    </div>

    <!-- Sidebar-Inhalt -->
    <div class="flex-1 overflow-y-auto p-2">
        <!-- Neuer Chat Button -->
        <button
            onclick={() => goto("/chat")}
            class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-light-tx dark:text-dark-tx
                   hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors"
        >
            <Plus class="w-4 h-4" />
            Neuer Chat
        </button>

        <!-- Assistenten -->
        <div class="mt-2">
            <div
                class="w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium text-light-tx dark:text-dark-tx
                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                       {$page.url.pathname.startsWith('/assistants') ? 'bg-light-ui-2 dark:bg-dark-ui-2' : ''}"
            >
                <button onclick={() => { assistantsOpen = true; goto('/assistants') }}>
                    <span class="flex items-center gap-2">
                        <Bot class="w-4 h-4" />
                        Assistenten
                    </span>
                </button>
                {#if $user?.roles.includes('admin')}
                    <button onclick={toggleAssistants}>
                        {#if assistantsOpen}
                            <ChevronDown class="w-4 h-4" />
                        {:else}
                            <ChevronRight class="w-4 h-4" />
                        {/if}
                    </button>
                {/if}
            </div>
            {#if assistantsOpen && $user?.roles.includes('admin')}
                <div class="mt-1 space-y-1 pl-2">
                    <button
                        onclick={() => goto('/assistants/manage')}
                        class="w-full text-left px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                               hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors
                               {$page.url.pathname === '/assistants/manage'
                                    ? 'bg-light-ui-2 dark:bg-dark-ui-2' : ''}"
                    >
                        <span class="flex items-center gap-2">
                            <Settings class="w-4 h-4" />
                            Verwalten
                        </span>
                    </button>
                </div>
            {/if}
        </div>

        <!-- Letzte Chats Sektion -->
        <div class="mt-2">
            <div
                class="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-light-tx dark:text-dark-tx hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors rounded-lg"
            >
                <button
                    onclick={() => {
                        openRecentChats();
                        goto("/history");
                    }}
                >
                    <span class="flex items-center gap-2">
                        <History class="w-4 h-4" />
                        Letzte Chats
                    </span>
                </button>
                <button onclick={toggleRecentChats}>
                    <span class="flex items-center gap-2">
                        {#if recentChatsOpen}
                            <ChevronDown class="w-4 h-4" />
                        {:else}
                            <ChevronRight class="w-4 h-4" />
                        {/if}
                    </span>
                </button>
            </div>

            {#if recentChatsOpen}
                <div class="mt-1 space-y-1 pl-2">
                    {#if $recentConversations.length === 0}
                        <p
                            class="text-sm text-light-tx-3 dark:text-dark-tx-3 px-3 py-1"
                        >
                            Noch keine Chats
                        </p>
                    {:else}
                        {#each $recentConversations as conv}
                            {@const convColor = conv.subject_id != null
                                ? ($subjectMap[conv.subject_id]?.color ?? null)
                                : null}
                            <button
                                onclick={() => goto(`/chat?id=${conv.id}`)}
                                class="w-full text-left px-3 py-2 text-sm rounded-lg text-light-tx dark:text-dark-tx
                                       hover:bg-light-ui-2 dark:hover:bg-dark-ui-2 transition-colors relative overflow-hidden
                                       {conv.id === currentConversationId
                                    ? 'bg-light-ui-2 dark:bg-dark-ui-2'
                                    : ''}"
                            >
                                <!-- Farbstreifen links (nur wenn Fach mit Farbe) -->
                                {#if convColor}
                                    <span
                                        class="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg"
                                        style="background-color: {convColor}"
                                    ></span>
                                {/if}
                                <div
                                    class="flex justify-between items-center gap-1"
                                >
                                    <div
                                        class="flex items-center gap-1 min-w-0"
                                    >
                                        {#if conv.assistant_name}
                                            <Bot
                                                class="w-3 h-3 shrink-0 text-light-bl dark:text-dark-bl"
                                                title={conv.assistant_name}
                                            />
                                        {/if}
                                        <span
                                            class="truncate"
                                            title={conv.title ??
                                                "Unbenannter Chat"}
                                        >
                                            {conv.title ?? "Unbenannter Chat"}
                                        </span>
                                    </div>
                                    <span
                                        class="text-xs text-light-tx-3 dark:text-dark-tx-3 whitespace-nowrap"
                                    >
                                        {formatDate(conv.last_message_at)}
                                    </span>
                                    <ConversationMenu
                                        conversationId={conv.id}
                                        title={conv.title}
                                        subject_id={conv.subject_id}
                                        onDelete={handleDeleted}
                                        iconSize={12}
                                    />
                                </div>
                            </button>
                        {/each}
                    {/if}
                </div>
            {/if}
        </div>
    </div>

    <!-- Unterer Bereich -->
    <SidebarBottom />
</aside>
